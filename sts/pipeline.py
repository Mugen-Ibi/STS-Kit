"""Bounded text-to-speech pipeline with structured cancellation."""
import asyncio


async def stream_speech(produce, emit):
    queue = asyncio.Queue(maxsize=2)

    async def consume():
        while True:
            sentence = await queue.get()
            if sentence is None:
                return
            await emit(sentence)

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(produce(queue))
            group.create_task(consume())
    except ExceptionGroup as errors:
        # Preserve actionable errors for the UI, after all siblings have stopped.
        error = errors
        while isinstance(error, BaseExceptionGroup):
            error = error.exceptions[0]
        raise error from None
