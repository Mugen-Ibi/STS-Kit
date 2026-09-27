import asyncio
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from websockets.asyncio.client import connect
from smoke_test import turn

ROOT = Path(__file__).resolve().parents[1]


async def main():
    engine = sys.argv[1] if len(sys.argv) > 1 else 'sbv2'
    async with connect("ws://127.0.0.1:8765/ws", origin="http://127.0.0.1:8765", max_size=8_000_000) as ws:
        await ws.send(json.dumps({"type": "message", "audio": "bad base64!"}))
        msg = json.loads(await ws.recv())
        assert msg["type"] == "error", msg
        await ws.send(json.dumps({"type": "message", "text": "日本について詳しく説明してください。", "engine": engine, "request_id": "cancel-test"}))
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), 30))
            assert message['type'] != 'error', message
            if message['type'] == 'token':
                assert message['request_id'] == 'cancel-test'
                break
        await ws.send(json.dumps({"type": "cancel"}))
        while json.loads(await ws.recv())["type"] != "cancelled":
            pass
        samples, rate = sf.read(ROOT / "run/speech-question.wav")
        extended = np.tile(samples, 30)[:int(rate * 27)]
        # Browser-sized WAV input, normalized by the server.
        buf = io.BytesIO()
        sf.write(buf, extended, rate, format="WAV", subtype="PCM_16")
        result = await turn(ws, {"audio": base64.b64encode(buf.getvalue()).decode(), "engine": engine}, "long-response")
        assert "東京" in result["answer"], result
        result["input_seconds"] = len(extended) / rate
        print(json.dumps(result, ensure_ascii=False), flush=True)
        (ROOT / 'run' / f'limits-results-{engine}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


asyncio.run(main())
