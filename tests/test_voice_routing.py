import asyncio
import pytest
from sts import app


class Socket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


@pytest.mark.parametrize('engine,speaker', [('qwen3', 'ono_anna'), ('cosy3', 'JVNV F1 参照')])
def test_preview_routes_without_llm_or_history(monkeypatch, engine, speaker):
    calls = []
    monkeypatch.setattr(app, 'ready', True)
    monkeypatch.setattr(app, 'pipeline_lock', asyncio.Lock())
    def synthesize(*args):
        calls.append(args)
        return b'local audio', 1.0
    monkeypatch.setattr(app.voice, 'synthesize', synthesize)
    ws, history = Socket(), [{'role': 'user', 'content': '以前の会話'}]
    asyncio.run(app.respond(ws, dict(type='preview', text='こんにちは。', engine=engine, speaker=speaker), history))
    assert calls == [('こんにちは。', 'Neutral', 1.0, 1.0, engine, speaker)]
    assert history == [{'role': 'user', 'content': '以前の会話'}]
    assert [e['type'] for e in ws.events if e['type'] != 'status'] == ['token', 'audio', 'done']
    assert next(e for e in ws.events if e['type'] == 'audio')['preview'] is True


@pytest.mark.parametrize('fields', [dict(engine='unknown'), dict(engine='qwen3', style='Happy'),
    dict(engine='lfm', speed=1.15), dict(engine='qwen3', style_weight=3),
    dict(engine='lfm', speaker='ono_anna'), dict(engine='sbv2', style_weight=float('nan')),
    dict(engine='lfm', text='長' * 201), dict(engine='cosy3', style='Happy')])
def test_invalid_model_settings_fail_before_inference(monkeypatch, fields):
    monkeypatch.setattr(app, 'ready', True)
    with pytest.raises(ValueError):
        asyncio.run(app.respond(Socket(), dict(type='preview', **{'text': 'こんにちは。', **fields}), []))
