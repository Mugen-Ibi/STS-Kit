"""Opt-in authentication boundary for a loopback service behind Tailscale Serve."""
import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import HTMLResponse, Response

COOKIE = '__Host-sts-session'
LOGIN = """<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>STS Kit 接続</title>
<h1>STS Kit に接続</h1><form><label>接続トークン
<input id="token" type="password" autocomplete="off" required></label>
<button>接続</button></form><p id="status"></p><script>
document.querySelector('form').onsubmit = async (e) => {
  e.preventDefault();
  const input = document.getElementById('token'), token = input.value;
  input.value = '';
  try {
    const r = await fetch('/api/session', {method: 'POST',
      headers: {Authorization: 'Bearer ' + token}, signal: AbortSignal.timeout(10000)});
    if (r.ok) location.replace('/');
    else document.getElementById('status').textContent = '接続できません。トークンと設定を確認してください。';
  } catch { document.getElementById('status').textContent = '通信できません。接続を確認してください。'; }
};
</script></html>"""


class RemoteAccess:
    def __init__(self, config):
        self.enabled = config.get('remote_enabled', False)
        if not isinstance(self.enabled, bool):
            raise ValueError('remote_enabled must be a boolean')
        self.origin = config.get('remote_origin', '')
        self.token = os.environ.get('STS_REMOTE_TOKEN', '') if self.enabled else ''
        self.session_key = secrets.token_bytes(32)  # Memory only; restart revokes cookies.
        self.timeout = config.get('remote_request_timeout_s', 180)
        if self.enabled:
            if not isinstance(self.origin, str) or not re.fullmatch(
                    r'https://[a-z0-9-]+\.[a-z0-9-]+\.ts\.net', self.origin):
                raise ValueError('remote_origin must be an exact https://host.tailnet.ts.net origin')
            if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', self.token):
                raise ValueError('STS_REMOTE_TOKEN must contain 32-256 URL-safe characters')
            if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)) or not 10 <= self.timeout <= 600:
                raise ValueError('remote_request_timeout_s must be between 10 and 600')
        self.host = urlsplit(self.origin).netloc if self.enabled else ''
        self.local_hosts = {'localhost', '127.0.0.1', 'testserver',
                            f"localhost:{config['web_port']}", f"127.0.0.1:{config['web_port']}"}
        self.local_origins = {f"http://localhost:{config['web_port']}",
                              f"http://127.0.0.1:{config['web_port']}"}

    def bearer(self, headers):
        supplied = headers.get('authorization', '')
        return hmac.compare_digest(supplied.encode(), ('Bearer ' + self.token).encode())

    def cookie(self):
        expiry = str(int(time.time()) + 12 * 3600)
        signature = hmac.new(self.session_key, expiry.encode(), hashlib.sha256).hexdigest()
        return expiry + '.' + signature

    def authenticated(self, scope):
        headers = Headers(scope=scope)
        if self.bearer(headers):
            return True
        value = HTTPConnection(scope).cookies.get(COOKIE, '')
        try:
            expiry, signature = value.split('.')
            expected = hmac.new(self.session_key, expiry.encode(), hashlib.sha256).hexdigest()
            return int(expiry) > time.time() and hmac.compare_digest(signature, expected)
        except (ValueError, TypeError):
            return False

    def permitted(self, scope):
        headers = Headers(scope=scope)
        host = headers.get('host', '').lower()
        origin = headers.get('origin')
        if not self.enabled:
            return host in self.local_hosts and (scope['type'] != 'websocket' or origin in self.local_origins)
        # Forwarded headers never bypass host/origin or application authentication.
        if host not in self.local_hosts | {self.host}:
            return False
        if origin is not None and origin != self.origin:
            return False
        # Cookies are browser credentials: a WebSocket must carry the exact origin.
        if scope['type'] == 'websocket' and origin is None and not self.bearer(headers):
            return False
        return True


class AccessMiddleware:
    def __init__(self, app, policy):
        self.app, self.policy = app, policy

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        policy = self.policy

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = list(message.get('headers', [])) + [
                    (b'cache-control', b'no-store'), (b'referrer-policy', b'no-referrer'),
                    (b'x-content-type-options', b'nosniff'), (b'x-frame-options', b'DENY')]
            await send(message)

        async def reject(status):
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            else:
                await Response('Access denied', status_code=status)(scope, receive, secured_send)

        if not policy.permitted(scope):
            return await reject(403)
        if policy.enabled:
            headers = Headers(scope=scope)
            if scope['type'] == 'http' and scope['path'] == '/api/session':
                if (scope['method'] != 'POST' or headers.get('origin') != policy.origin
                        or not policy.bearer(headers)):
                    return await reject(401)
                response = Response(status_code=204)
                response.set_cookie(COOKIE, policy.cookie(), secure=True, httponly=True,
                                    samesite='strict', path='/')
                return await response(scope, receive, secured_send)
            if not policy.authenticated(scope):
                if scope['type'] == 'http' and scope['path'] == '/' and scope['method'] == 'GET':
                    return await HTMLResponse(LOGIN)(scope, receive, secured_send)
                return await reject(401)
        await self.app(scope, receive, secured_send)
