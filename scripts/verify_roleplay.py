"""Live regression: fictional facts, replacement world, and audio input/output."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sts.scenario import default_scenario
from smoke_test import turn


async def apply(ws, scenario):
    await ws.send(json.dumps({'type': 'scenario', 'scenario': scenario}, ensure_ascii=False))
    event = json.loads(await ws.recv())
    assert event['type'] == 'scenario_applied', event


async def main():
    async with httpx.AsyncClient(trust_env=False) as client:
        for _ in range(120):
            try:
                if (await client.get('http://127.0.0.1:8765/api/health')).json()['ready']:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError('App not ready')
    results = {}
    async with connect('ws://127.0.0.1:8765/ws', origin='http://127.0.0.1:8765', max_size=8_000_000) as ws:
        await apply(ws, default_scenario())
        results['identity'] = await turn(ws, {'text': 'もしもし。あなたのお名前と、今が何年か教えてください。'}, 'roleplay-identity')
        assert '2030' in results['identity']['answer'] and '灯' in results['identity']['answer'], results
        # Generate a synthetic spoken question locally; no microphone or personal recording.
        await ws.send(json.dumps({'type': 'preview', 'text': '2027年の夏には何がありましたか。'}))
        question_audio = None
        while True:
            event = json.loads(await ws.recv())
            if event['type'] == 'audio':
                question_audio = event['data']
            if event['type'] == 'error':
                raise RuntimeError(event)
            if event['type'] == 'done':
                break
        assert question_audio
        results['audio_history'] = await turn(ws, {'audio': question_audio}, 'roleplay-history')
        assert '2027' in results['audio_history']['transcript'], results
        assert any(word in results['audio_history']['answer'] for word in ['暑', '涼み番', '麦茶']), results
        alternate = dict(enabled=True, name='test-world.md', markdown='# 別の架空史\n2030年の日本。あなたの名前は七海。\n2028年に開業した地域バスの愛称は「こはく号」。車体は紫色。灯という人物はこの世界にはいない。')
        await apply(ws, alternate)
        results['replacement'] = await turn(ws, {'text': 'あなたの名前と、2028年に開業したバスの愛称を教えて。'}, 'roleplay-replacement')
        assert '七海' in results['replacement']['answer'] and 'こはく' in results['replacement']['answer'], results
        await apply(ws, {**alternate, 'enabled': False})
        results['disabled'] = await turn(ws, {'text': 'あなたは朝倉灯や七海という未来人ですか？'}, 'roleplay-disabled')
    (ROOT / 'run/roleplay-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
