import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from sts import app
from sts.scenario import default_scenario, system_prompt, validate_scenario


def world(text='# 別の歴史\n2030年、街のシンボルは青い時計。', enabled=True):
    return dict(enabled=enabled, name='history.md', markdown=text)


def test_bundled_world_and_disabled_prompt():
    value = default_scenario()
    assert '朝倉 灯' in value['markdown']
    assert '2027年' in system_prompt('通常会話', value)
    assert system_prompt('通常会話', {**value, 'enabled': False}) == '通常会話'
    assert validate_scenario(world('\ufeff# 歴史\n2030年'))['markdown'].startswith('#')


@pytest.mark.parametrize('value', [None, {}, world(''), world('a' * 4001), world('a\x00b'),
    {**world(), 'name': 'history.html'}, {**world(), 'enabled': 'true'},
    {**world(), 'markdown': ['a']}])
def test_reject_invalid_world(value):
    with pytest.raises(ValueError):
        validate_scenario(value)


def test_socket_world_switch_reset_isolation_and_invalid_retention(monkeypatch):
    async def fake_respond(ws, message, history, scenario=None, budget=None):
        await ws.send_json({'type': 'observed', 'scenario': scenario, 'history': list(history)})
        history.extend([{'role': 'user', 'content': message['text']},
                        {'role': 'assistant', 'content': 'reply'}])
    monkeypatch.setattr(app, 'respond', fake_respond)
    client = TestClient(app.app)  # No lifespan: models are not needed for session testing.
    headers = {'origin': 'http://127.0.0.1:8765'}
    with client.websocket_connect('/ws', headers=headers) as first, client.websocket_connect('/ws', headers=headers) as second:
        first.send_json({'type': 'scenario', 'scenario': world()})
        assert first.receive_json()['reset']
        first.send_json({'type': 'message', 'text': '質問'})
        assert first.receive_json()['scenario']['enabled']
        first.send_json({'type': 'scenario', 'scenario': world('')})
        assert first.receive_json()['type'] == 'error'
        first.send_json({'type': 'message', 'text': '続き'})
        event = first.receive_json()
        assert len(event['history']) == 2 and event['scenario'] == world()
        first.send_json({'type': 'scenario', 'scenario': world()})
        assert first.receive_json()['reset']
        first.send_json({'type': 'message', 'text': '同じファイルを再適用'})
        assert first.receive_json()['history'] == []
        first.send_json({'type': 'scenario', 'scenario': world('# 新しい歴史')})
        assert first.receive_json()['reset']
        first.send_json({'type': 'message', 'text': '別の質問'})
        assert first.receive_json()['history'] == []
        first.send_json({'type': 'reset'})
        assert first.receive_json()['type'] == 'cancelled'
        first.send_json({'type': 'message', 'text': '最初から'})
        event = first.receive_json()
        assert event['history'] == [] and event['scenario']['enabled']
        first.send_json({'type': 'scenario', 'scenario': world(enabled=False)})
        assert first.receive_json()['scenario']['enabled'] is False
        second.send_json({'type': 'message', 'text': '別の接続'})
        assert second.receive_json()['scenario'] is None


def test_context_drops_oldest_pair_but_never_world_or_question(monkeypatch):
    monkeypatch.setitem(app.config, 'context_size', 800)
    monkeypatch.setitem(app.config, 'max_tokens', 180)
    class Client:
        async def post(self, url, headers, json):
            size = 500 if 'old question' in json['content'] else 50
            class Response:
                def raise_for_status(self):
                    pass
                def json(self):
                    return {'tokens': [0] * size}
            return Response()
    messages = [{'role': 'system', 'content': 'world' * 180}, {'role': 'user', 'content': 'old question'},
                {'role': 'assistant', 'content': 'old answer'}, {'role': 'user', 'content': 'new question'}]
    assert asyncio.run(app.fit_context(Client(), messages)) == [messages[0], messages[-1]]
    assert len(messages) == 4
    with pytest.raises(ValueError, match='長すぎ'):
        asyncio.run(app.fit_context(Client(), [messages[0], messages[1]]))
