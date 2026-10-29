"""Malformed client input must not destroy an otherwise valid conversation."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sts import app


@pytest.mark.parametrize('kind', [[], {}, None, 1, True])
def test_invalid_operation_type_keeps_connection_usable(kind):
    client = TestClient(app.app)  # Deliberately skip GPU/model lifespan.
    with client.websocket_connect('/ws', headers={'origin': 'http://127.0.0.1:8765'}) as ws:
        ws.send_json({'type': kind})
        assert ws.receive_json()['type'] == 'error'
        ws.send_json({'type': 'reset'})
        assert ws.receive_json()['type'] == 'cancelled'


@pytest.mark.parametrize('origin', [None, 'https://example.invalid', 'http://127.0.0.1:8766'])
def test_untrusted_origin_cannot_open_conversation(origin):
    client = TestClient(app.app)
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect('/ws', headers={'origin': origin} if origin else {}):
            pass
    assert rejected.value.code == 1008


def test_binary_frames_close_with_unsupported_data_code():
    client = TestClient(app.app)
    with client.websocket_connect('/ws', headers={'origin': 'http://127.0.0.1:8765'}) as ws:
        ws.send_bytes(b'not a JSON text frame')
        with pytest.raises(WebSocketDisconnect) as rejected:
            ws.receive_json()
        assert rejected.value.code == 1003


def test_deep_json_keeps_connection_usable():
    client = TestClient(app.app)
    with client.websocket_connect('/ws', headers={'origin': 'http://127.0.0.1:8765'}) as ws:
        ws.send_text('{"type":"reset","ignored":' + '[' * 10000 + '0' + ']' * 10000 + '}')
        assert ws.receive_json()['type'] == 'error'
        ws.send_json({'type': 'reset'})
        assert ws.receive_json()['type'] == 'cancelled'
