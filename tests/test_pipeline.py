import asyncio

import pytest

from sts.pipeline import stream_speech
from sts.audio import take_sentence
from sts.context import ContextBudget


def test_first_clause_and_stream_text_preservation():
    text = '2030年の暮らしには変わった点がありますが、昔からの習慣も残っています。'
    head, tail = take_sentence(text, first=True)
    assert head.endswith('、') and head + tail == text
    assert take_sentence('はい、まだ途中', first=True)[0] == ''
    text = 'あ' * 180 + '。続き'
    a, rest = take_sentence(text, max_chars=80)
    assert len(a) == 80 and a + rest == text


def test_generation_continues_during_tts_and_preserves_order():
    async def run():
        generating = asyncio.Event()
        delivered = []
        async def produce(queue):
            await queue.put('first')
            await asyncio.sleep(0)
            generating.set()
            await queue.put('second')
            await queue.put(None)
        async def emit(sentence):
            await asyncio.wait_for(generating.wait(), 1)
            delivered.append(sentence)
        await stream_speech(produce, emit)
        assert delivered == ['first', 'second']
    asyncio.run(run())


def test_failure_cancels_producer_instead_of_deadlocking_full_queue():
    async def run():
        stopped = asyncio.Event()
        async def produce(queue):
            try:
                for i in range(100):
                    await queue.put(str(i))
                await queue.put(None)
            finally:
                stopped.set()
        async def emit(sentence):
            raise ValueError('TTS failed')
        with pytest.raises(ValueError, match='TTS failed'):
            await asyncio.wait_for(stream_speech(produce, emit), 1)
        assert stopped.is_set()
    asyncio.run(run())


def test_cancel_waits_for_inflight_inference_and_discards_pending_audio():
    async def run():
        entered, finished = asyncio.Event(), asyncio.Event()
        delivered = []
        async def produce(queue):
            await queue.put('first')
            await queue.put('discard me')
            await queue.put(None)
        async def emit(sentence):
            work = asyncio.create_task(asyncio.sleep(.03))
            entered.set()
            try:
                await asyncio.shield(work)
            except asyncio.CancelledError:
                await work
                finished.set()
                raise
            delivered.append(sentence)
        task = asyncio.create_task(stream_speech(produce, emit))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert finished.is_set() and delivered == []
    asyncio.run(run())


def test_context_counts_cached_without_keeping_text():
    class Client:
        calls = 0
        async def post(self, *args, **kwargs):
            self.calls += 1
            class Response:
                def raise_for_status(self): pass
                def json(self): return {'tokens': [1] * 50}
            return Response()
    async def run():
        client, budget = Client(), ContextBudget()
        messages = [{'role': 'system', 'content': '世界' * 300}, {'role': 'user', 'content': '質問'}]
        for _ in range(2):
            assert await budget.fit(client, messages, 800, 180, 1, {}) == messages
        assert client.calls == 2
        assert all(isinstance(key, bytes) for key in budget.counts)
    asyncio.run(run())
