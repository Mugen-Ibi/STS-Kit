"""Exercise running server over its public WebSocket; no microphone is accessed."""
import asyncio
import base64
import io
import json
import subprocess
import sys
from pathlib import Path

import soundfile as sf
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]


async def turn(ws, payload, output):
    await ws.send(json.dumps({"type": "message", **payload}, ensure_ascii=False))
    answer = ""
    transcript = None
    count = 0
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 180))
        if msg["type"] == "error":
            raise RuntimeError(msg["text"])
        if msg["type"] == "token":
            answer += msg["text"]
        if msg["type"] == "transcript":
            transcript = msg["text"]
        if msg["type"] == "audio":
            data = base64.b64decode(msg["data"])
            audio, rate = sf.read(io.BytesIO(data))
            assert len(audio) > rate * 0.1
            (ROOT / "run" / f"{output}-{count}.wav").write_bytes(data)
            count += 1
        if msg["type"] == "done":
            assert answer.strip() and count > 0
            return {"answer": answer, "transcript": transcript, "chunks": count, **msg["metrics"]}


async def main():
    engine = sys.argv[1] if len(sys.argv) > 1 else 'sbv2'
    if not (ROOT / "run/speech-question.wav").exists():
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/make_fixture.py")], check=True)
    results = {}
    async with connect("ws://127.0.0.1:8765/ws", origin="http://127.0.0.1:8765", max_size=8_000_000) as ws:
        results["text"] = await turn(ws, {"text": "こんにちは。日本の首都を一言で教えてください。", "engine": engine}, "text-response")
        print(json.dumps(results["text"], ensure_ascii=False), flush=True)
        await ws.send(json.dumps({"type": "reset"}))
        await ws.recv()
        wav = (ROOT / "run/speech-question.wav").read_bytes()
        results["speech"] = await turn(ws, {"audio": base64.b64encode(wav).decode(), "engine": engine}, "speech-response")
        reply = results["speech"]["answer"]
        assert "東京" in reply and "ありません" not in reply, results["speech"]
        assert "首都" in results["speech"]["transcript"], results["speech"]
        print(json.dumps(results["speech"], ensure_ascii=False), flush=True)
    (ROOT / "run" / f"smoke-results-{engine}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
