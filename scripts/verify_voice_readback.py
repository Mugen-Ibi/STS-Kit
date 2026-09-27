"""A limited ASR sanity check of generated Japanese, not a listening-quality score."""
import asyncio
import base64
import json
import sys
from pathlib import Path
import websockets

ROOT = Path(__file__).resolve().parents[1]
async def main():
    results = {}
    async with websockets.connect('ws://127.0.0.1:8765/ws', origin='http://127.0.0.1:8765', max_size=8000000) as ws:
        for engine in sys.argv[1:] or ['sbv2', 'qwen3', 'lfm', 'cosy3']:
            wav = (ROOT / f'run/voice-comparison/{engine}-1.wav').read_bytes()
            await ws.send(json.dumps({'audio': base64.b64encode(wav).decode()}))
            transcript = None
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), 240))
                if event['type'] == 'error':
                    raise RuntimeError(event['text'])
                if event['type'] == 'transcript':
                    transcript = event['text']
                    await ws.send(json.dumps({'type': 'cancel'}))
                if event['type'] == 'cancelled':
                    break
            results[engine] = transcript
            print(engine, transcript, flush=True)
            assert transcript and 'こんにちは' in transcript and '天気' in transcript
    (ROOT / 'run/voice-comparison/readback.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
asyncio.run(main())
