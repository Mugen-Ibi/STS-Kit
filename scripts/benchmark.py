"""Repeatable localhost latency benchmark. Saves synthetic test data, never microphone audio."""
import argparse
import asyncio
import base64
import io
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sts.scenario import default_scenario


async def request(ws, payload):
    begin = time.perf_counter()
    await ws.send(json.dumps(payload, ensure_ascii=False))
    answer, first, onset = '', None, 0
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 180))
        if msg['type'] == 'error':
            raise RuntimeError(msg['text'])
        if msg['type'] == 'token':
            answer += msg['text']
        if msg['type'] == 'audio' and first is None:
            first = time.perf_counter() - begin
            samples, rate = sf.read(io.BytesIO(base64.b64decode(msg['data'])))
            assert np.isfinite(samples).all() and np.max(np.abs(samples)) > .001
            indices = np.flatnonzero(np.abs(samples) > max(.002, np.max(np.abs(samples)) * .02))
            onset = indices[0] / rate if len(indices) else 0
        if msg['type'] == 'done':
            return dict(client_first_audio_s=first, client_total_s=time.perf_counter() - begin,
                        audio_onset_s=onset, answer=answer, **msg['metrics'])


async def main(args):
    results = {}
    async with connect('ws://127.0.0.1:8765/ws', origin='http://127.0.0.1:8765', max_size=8_000_000) as ws:
        for name, text in [('short', 'こんにちは。今日はいい天気ですね。'),
                           ('long', '2027年の夏は、東日本を中心に猛暑が長引いて、墨田区の商店街で涼み番が始まったのを覚えています。')]:
            await request(ws, dict(type='preview', text=text))
            results['tts_' + name] = [await request(ws, dict(type='preview', text=text)) for _ in range(args.rounds)]
        scenario = default_scenario()
        await ws.send(json.dumps(dict(type='scenario', scenario=scenario), ensure_ascii=False))
        assert json.loads(await ws.recv())['type'] == 'scenario_applied'
        cases = {'dialogue': dict(text='2027年の夏はどんな様子でしたか。あなたの体験も教えてください。')}
        fixture = ROOT / 'run/speech-question.wav'
        if fixture.exists():
            cases['speech'] = dict(audio=base64.b64encode(fixture.read_bytes()).decode())
        for name, payload in cases.items():
            results[name] = []
            for index in range(args.rounds + 1):
                await ws.send(json.dumps(dict(type='reset')))
                assert json.loads(await ws.recv())['type'] == 'cancelled'
                result = await request(ws, dict(type='message', **payload))
                if index:
                    results[name].append(result)
    summary = {name: {key: dict(median=statistics.median(row[key] for row in rows),
                                p95=float(np.percentile([row[key] for row in rows], 95)))
                     for key in ['client_first_audio_s', 'client_total_s', 'tts_s']}
               for name, rows in results.items()}
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(rounds=args.rounds, summary=summary, results=results), ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=7)
    parser.add_argument('--output', default='run/performance.json')
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100:
        parser.error('rounds must be 1..100')
    asyncio.run(main(args))
