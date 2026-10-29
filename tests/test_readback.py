import asyncio
import base64
import json

import pytest

from scripts.verify_voice_readback import readback


class Socket:
    def __init__(self, events):
        self.events = iter(events)
        self.sent = []

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def recv(self):
        return json.dumps(next(self.events))


def test_readback_uses_message_protocol_and_waits_for_cancel_acknowledgement():
    ws = Socket([{'type': 'status'}, {'type': 'transcript', 'text': 'こんにちは。天気。'},
                 {'type': 'token', 'text': 'discard this'}, {'type': 'cancelled'}])
    assert asyncio.run(readback(ws, b'synthetic wav')) == 'こんにちは。天気。'
    assert ws.sent == [{'type': 'message', 'audio': base64.b64encode(b'synthetic wav').decode()},
                       {'type': 'cancel'}]


def test_readback_surfaces_server_error():
    ws = Socket([{'type': 'error', 'text': 'invalid audio'}])
    with pytest.raises(RuntimeError, match='invalid audio'):
        asyncio.run(readback(ws, b'bad input'))
