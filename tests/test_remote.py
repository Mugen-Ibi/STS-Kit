import asyncio
import threading

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sts import app as application
from sts.remote import AccessMiddleware, COOKIE, RemoteAccess

ORIGIN = 'https://home.example-tailnet.ts.net'
TOKEN = 'test-only-not-a-real-credential-' + 'x' * 32


@pytest.fixture
def policy(monkeypatch):
    monkeypatch.setenv('STS_REMOTE_TOKEN', TOKEN)
    return RemoteAccess(dict(web_port=8765, remote_enabled=True, remote_origin=ORIGIN))


def client_for(policy):
    app = FastAPI()
    app.add_middleware(AccessMiddleware, policy=policy)

    @app.get('/api/health')
    def health():
        return {'ready': True}

    @app.websocket('/ws')
    async def socket(ws: WebSocket):
        await ws.accept()
        await ws.send_json({'type': 'ready'})

    return TestClient(app, base_url=ORIGIN)


@pytest.mark.parametrize('change', [dict(remote_enabled='false'), dict(remote_origin='http://home.example-tailnet.ts.net'),
    dict(remote_origin=ORIGIN + '/'), dict(remote_origin='https://evil.test'),
    dict(remote_origin=ORIGIN + ':443'), dict(remote_request_timeout_s=0), dict(remote_request_timeout_s=float('nan'))])
def test_fail_closed(policy, change):
    with pytest.raises(ValueError):
        RemoteAccess(dict(web_port=8765, remote_enabled=True, remote_origin=ORIGIN) | change)


def test_missing_token_rejected(monkeypatch):
    monkeypatch.delenv('STS_REMOTE_TOKEN', raising=False)
    with pytest.raises(ValueError, match='STS_REMOTE_TOKEN'):
        RemoteAccess(dict(web_port=8765, remote_enabled=True, remote_origin=ORIGIN))


def test_http_boundary_and_cookie(policy):
    client = client_for(policy)
    assert client.get('/').status_code == 200  # Login shell only.
    assert client.get('/api/health').status_code == 401
    assert client.get('/static/app.js').status_code == 401
    assert client.get('/api/health?token=' + TOKEN).status_code == 401
    auth = {'Authorization': 'Bearer ' + TOKEN}
    assert client.get('/api/health', headers=auth).json()['ready']
    assert client.get('/api/health', headers={**auth, 'Host': 'evil.test'}).status_code == 403
    assert client.get('/api/health', headers={**auth, 'Origin': 'https://evil.test'}).status_code == 403
    assert client.get('/api/health', headers={'Host': '127.0.0.1:8765', 'X-Forwarded-Host': ORIGIN[8:],
        'Tailscale-User-Login': 'owner@example.test'}).status_code == 401
    assert client.post('/api/session', headers=auth).status_code == 401
    result = client.post('/api/session', headers={**auth, 'Origin': ORIGIN})
    assert result.status_code == 204
    cookie = result.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
    assert TOKEN not in cookie and 'no-store' in result.headers['cache-control']
    assert client.get('/api/health').status_code == 200
    with client.websocket_connect('wss://home.example-tailnet.ts.net/ws', headers={'Origin': ORIGIN}) as ws:
        assert ws.receive_json()['type'] == 'ready'
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws'):
            pass  # Cookie without origin is not a native client credential.


def test_ws_authentication_and_origin(policy):
    client = client_for(policy)
    for headers in ({'Origin': ORIGIN}, {'Origin': 'https://evil.test', 'Authorization': 'Bearer ' + TOKEN},
                    {'Origin': ORIGIN, 'Authorization': 'Bearer wrong'}):
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect('/ws', headers=headers):
                pass
        assert error.value.code == 1008
    with client.websocket_connect('/ws', headers={'Authorization': 'Bearer ' + TOKEN}) as ws:
        assert ws.receive_json()['type'] == 'ready'


def test_expired_tampered_and_restart_cookies(policy, monkeypatch):
    client = client_for(policy)
    cookie = policy.cookie()
    assert client.get('/api/health', headers={'Cookie': f'{COOKIE}={cookie}'}).status_code == 200
    assert client.get('/api/health', headers={'Cookie': f'{COOKIE}={cookie}x'}).status_code == 401
    with monkeypatch.context() as clock:
        clock.setattr('sts.remote.time.time', lambda: 10**12)
        assert client.get('/api/health', headers={'Cookie': f'{COOKIE}={cookie}'}).status_code == 401
    policy.session_key = b'different-test-key'
    assert client.get('/api/health', headers={'Cookie': f'{COOKIE}={cookie}'}).status_code == 401


def test_local_default_is_unchanged():
    policy = RemoteAccess(dict(web_port=8765))
    client = client_for(policy)
    assert client.get('/api/health').status_code == 403
    assert client.get('/api/health', headers={'Host': 'localhost:8765'}).status_code == 200
    with client.websocket_connect('/ws', headers={'Host': 'localhost:8765', 'Origin': 'http://localhost:8765'}) as ws:
        assert ws.receive_json()['type'] == 'ready'


@pytest.fixture
def real_client(policy, monkeypatch):
    # Actual conversation handler, no lifespan/model loading; install fresh middleware.
    monkeypatch.setattr(application, 'access', policy)
    shell = FastAPI()
    shell.add_api_websocket_route('/ws', application.conversation)
    shell.add_api_route('/api/health', application.health)
    shell.add_middleware(AccessMiddleware, policy=policy)
    return TestClient(shell, base_url=ORIGIN, headers={'Authorization': 'Bearer ' + TOKEN})


def test_stream_cancel_disconnect_and_ping(real_client, monkeypatch):
    stopped = threading.Event()

    async def respond(ws, message, *args):
        try:
            await ws.send_json({'type': 'audio', 'data': 'synthetic-wav', 'text': 'test'})
            await asyncio.Event().wait()
        finally:
            stopped.set()
    monkeypatch.setattr(application, 'respond', respond)
    with real_client.websocket_connect('wss://home.example-tailnet.ts.net/ws', headers={'Origin': ORIGIN}) as ws:
        ws.send_json({'type': 'message', 'text': 'test', 'request_id': 42})
        assert ws.receive_json()['request_id'] == 42
        ws.send_json({'type': 'ping'})
        assert ws.receive_json()['type'] == 'pong'
        ws.send_json({'type': 'cancel'})
        assert ws.receive_json()['type'] == 'cancelled'
        assert stopped.wait(1)
        stopped.clear()
        ws.send_json({'type': 'message', 'text': 'again'})
        assert ws.receive_json()['type'] == 'audio'
    assert stopped.wait(1)


def test_timeout_and_error_redaction(real_client, policy, monkeypatch):
    policy.timeout = .02
    stopped = threading.Event()

    async def respond(*args):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    monkeypatch.setattr(application, 'respond', respond)
    with real_client.websocket_connect('wss://home.example-tailnet.ts.net/ws', headers={'Origin': ORIGIN}) as ws:
        ws.send_json({'type': 'message', 'text': 'test', 'request_id': 7})
        msg = ws.receive_json()
        assert 'timed out' in msg['text'] and msg['request_id'] == 7
        assert stopped.wait(1)

        async def fail(*args):
            raise RuntimeError('sensitive backend detail')
        monkeypatch.setattr(application, 'respond', fail)
        ws.send_json({'type': 'message', 'text': 'test'})
        assert 'sensitive' not in ws.receive_json()['text']


def test_health_redacts_backend_error(real_client, monkeypatch):
    from contextlib import asynccontextmanager
    class Backend:
        async def get(self, *args, **kwargs):
            class Result:
                status_code = 200
            return Result()
    @asynccontextmanager
    async def backend():
        yield Backend()
    monkeypatch.setattr(application, 'llama_client', backend)
    monkeypatch.setattr(application, 'startup_error', 'private backend path or credential')
    monkeypatch.setattr(application, 'ready', False)
    data = real_client.get('/api/health').json()
    assert data['remote_enabled'] and data['transport'] == 'https-wss'
    assert data['llm_ready'] and not data['ready']
    assert 'private' not in data['error']


def test_remote_sessions_keep_independent_history(real_client, monkeypatch):
    async def respond(ws, message, history, *args):
        prior = list(history)
        history.append(message['text'])
        await ws.send_json({'type': 'observed', 'history': prior})
    monkeypatch.setattr(application, 'respond', respond)
    with real_client.websocket_connect('/ws') as first, real_client.websocket_connect('/ws') as second:
        first.send_json({'type': 'message', 'text': 'one'})
        assert first.receive_json()['history'] == []
        second.send_json({'type': 'message', 'text': 'two'})
        assert second.receive_json()['history'] == []
        first.send_json({'type': 'message', 'text': 'three'})
        assert first.receive_json()['history'] == ['one']
        first.send_json({'type': 'reset'})
        assert first.receive_json()['type'] == 'cancelled'
        first.send_json({'type': 'message', 'text': 'four'})
        assert first.receive_json()['history'] == []
