"""Exercise the actual Uvicorn / websockets transport without loading any models."""
import asyncio
import json
import socket

import pytest
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError

from sts import app


def test_websockets17_loopback_transport_and_error_recovery(monkeypatch):
    # Diagnostic clients must bypass a configured proxy, even without NO_PROXY.
    monkeypatch.setenv('ws_proxy', 'http://127.0.0.1:1')
    monkeypatch.delenv('no_proxy', raising=False)
    monkeypatch.delenv('NO_PROXY', raising=False)

    async def run():
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app.app, lifespan='off', log_level='critical'))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async def started():
                while not server.started:
                    if task.done():
                        await task
                        raise AssertionError('server stopped before startup')
                    await asyncio.sleep(.01)
            await asyncio.wait_for(started(), 5)
            async with connect(f'ws://127.0.0.1:{port}/ws',
                               origin=f"http://127.0.0.1:{app.config['web_port']}",
                               proxy=None) as ws:
                for request, expected in [({'type': []}, 'error'),
                                          ({'type': 'reset'}, 'cancelled'),
                                          ({'type': 'cancel'}, 'cancelled')]:
                    await ws.send(json.dumps(request))
                    event = json.loads(await asyncio.wait_for(ws.recv(), 3))
                    assert event['type'] == expected
                await ws.send('{"type":"reset","ignored":' + '[' * 10000 + '0' + ']' * 10000 + '}')
                assert json.loads(await asyncio.wait_for(ws.recv(), 3))['type'] == 'error'
                await ws.send(json.dumps({'type': 'reset'}))
                assert json.loads(await asyncio.wait_for(ws.recv(), 3))['type'] == 'cancelled'
                await ws.send(b'unsupported binary frame')
                with pytest.raises(ConnectionClosedError) as closed:
                    await asyncio.wait_for(ws.recv(), 3)
                assert closed.value.rcvd.code == 1003
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 5)
            listener.close()

    asyncio.run(run())
