"""Model-free real HTTP/WS smoke test; binds only an ephemeral loopback port.

Run with the main environment: .venv/Scripts/python.exe scripts/test_remote_loopback.py
No VPN configuration, real credentials, microphone, model inference or audio files.
"""
import asyncio
import base64
import io
import os
from pathlib import Path
import socket
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import uvicorn
from fastapi import FastAPI
from websockets.asyncio.client import connect

from sts import app as application
from sts.remote import AccessMiddleware, RemoteAccess


async def main():
    token = 'loopback-test-only-' + 'x' * 40
    os.environ['STS_REMOTE_TOKEN'] = token
    origin = 'https://home.test-tailnet.ts.net'
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    policy = RemoteAccess(dict(web_port=port, remote_enabled=True, remote_origin=origin))
    application.access = policy
    stopped = asyncio.Event()
    wav = io.BytesIO()
    with wave.open(wav, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(320))
    encoded = base64.b64encode(wav.getvalue()).decode()

    async def respond(ws, message, *args):
        try:
            assert message['audio'] == encoded
            await ws.send_json({'type': 'audio', 'data': encoded})
            await asyncio.Event().wait()
        finally:
            stopped.set()

    application.respond = respond
    app = FastAPI()
    app.add_api_websocket_route('/ws', application.conversation)
    app.add_middleware(AccessMiddleware, policy=policy)
    @app.get('/api/health')
    def health():
        return {'ready': True, 'simulated': True}

    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
        lifespan='off', access_log=False, log_level='warning', proxy_headers=False))
    running = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            if running.done():
                await running
                raise RuntimeError('Server did not start')
            await asyncio.sleep(.05)
        assert server.started
        auth = {'Authorization': 'Bearer ' + token}
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            url = f'http://127.0.0.1:{port}/api/health'
            assert (await client.get(url)).status_code == 401
            assert (await client.get(url, headers=auth)).json()['simulated']
        import json
        async with connect(f'ws://127.0.0.1:{port}/ws', origin=origin, additional_headers=auth) as ws:
            await ws.send(json.dumps({'type': 'message', 'audio': encoded, 'request_id': 1}))
            packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert packet['data'] == encoded and packet['request_id'] == 1
            await ws.send('{"type":"ping"}')
            assert json.loads(await asyncio.wait_for(ws.recv(), 5))['type'] == 'pong'
            await ws.send('{"type":"cancel"}')
            assert json.loads(await asyncio.wait_for(ws.recv(), 5))['type'] == 'cancelled'
            assert stopped.is_set()
            stopped.clear()
            await ws.send(json.dumps({'type': 'message', 'audio': encoded, 'request_id': 2}))
            await asyncio.wait_for(ws.recv(), 5)
        await asyncio.wait_for(stopped.wait(), 5)
        print('PASS: loopback HTTP auth, WS synthetic WAV, heartbeat, cancellation, disconnect cleanup')
        print('Not tested: TLS termination, Tailscale, cross-network, models, microphone or hardware')
    finally:
        server.should_exit = True
        await asyncio.wait_for(running, 10)
        listener.close()
        os.environ.pop('STS_REMOTE_TOKEN', None)


if __name__ == '__main__':
    asyncio.run(main())
