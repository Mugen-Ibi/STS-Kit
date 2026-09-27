"""End-to-end preview tests while Gemma remains resident on GPU."""
import asyncio
import base64
import io
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
import websockets
import httpx

ROOT = Path(__file__).resolve().parents[1]
async def main():
    results = []
    async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
        for _ in range(90):
            try:
                if (await client.get('http://127.0.0.1:8765/api/health')).json()['ready']:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError('Server did not become ready')
    async with websockets.connect('ws://127.0.0.1:8765/ws', origin='http://127.0.0.1:8765', max_size=10000000) as ws:
        for engine in sys.argv[1:] or ['sbv2', 'qwen3', 'lfm', 'sbv2']:
            for repetition in range(2):
                await ws.send(json.dumps(dict(type='preview', text='こんにちは。今日はいい天気ですね。', engine=engine)))
                got_audio = False
                while True:
                    event = json.loads(await asyncio.wait_for(ws.recv(), timeout=300))
                    if event['type'] == 'error':
                        raise RuntimeError(event['text'])
                    if event['type'] == 'audio':
                        wav = base64.b64decode(event['data'])
                        samples, rate = sf.read(io.BytesIO(wav))
                        assert len(samples) > rate * .15 and np.max(np.abs(samples)) > .001
                        out = ROOT / 'run/voice-comparison'
                        out.mkdir(exist_ok=True, parents=True)
                        (out / f'{engine}-{repetition}.wav').write_bytes(wav)
                        got_audio = True
                    if event['type'] == 'done':
                        assert got_audio
                        result = dict(engine=engine, repetition=repetition, **event['metrics'])
                        results.append(result)
                        print(json.dumps(result), flush=True)
                        break
    (ROOT / 'run/voice-comparison/api-metrics.json').write_text(json.dumps(results, indent=2))
asyncio.run(main())
