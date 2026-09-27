import asyncio
import base64
import json
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .audio import normalize_wav, take_sentence
from .settings import ROOT, settings
from .voice_router import VoiceRouter, ENGINES
from .scenario import default_scenario, DEFAULT_FILE, validate_scenario, system_prompt
from .context import ContextBudget
from .pipeline import stream_speech

config = settings()
voice = VoiceRouter()
pipeline_lock = asyncio.Lock()
ready = False
startup_error = None
http_client = None


@asynccontextmanager
async def llama_client():
    if http_client is not None:
        yield http_client
    else:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120, connect=5)) as client:
            yield client


@asynccontextmanager
async def lifespan(app):
    global ready, startup_error, http_client
    http_client = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120, connect=5),
                                   limits=httpx.Limits(max_connections=8, max_keepalive_connections=8))
    try:
        await asyncio.to_thread(voice.load)
        warm_wav, _ = await asyncio.to_thread(voice.synthesize, "準備ができました。")
        warm_wav = normalize_wav(warm_wav)
        async with llama_client() as client:
            warm = await client.post(f"http://127.0.0.1:{config['llama_port']}/v1/chat/completions",
                headers={"Authorization": "Bearer " + os.environ.get("STS_LLAMA_API_KEY", "")},
                json={"model": "gemma-4-e2b", "max_tokens": 1, "id_slot": 0, "messages": [
                    {"role": "system", "content": config["system_prompt"]},
                    {"role": "user", "content": [
                        {"type": "text", "text": "この音声の発言に、日本語で短く返答してください。"},
                        {"type": "input_audio", "input_audio": {"data": base64.b64encode(warm_wav).decode(), "format": "wav"}}
                    ]}], "chat_template_kwargs": {"enable_thinking": False}})
            warm.raise_for_status()
        ready = True
    except Exception as exc:
        startup_error = str(exc)
        logging.exception("Voice initialization failed")
    try:
        yield
    finally:
        ready = False
        voice.close()
        await http_client.aclose()
        http_client = None


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def local_only(request: Request, call_next):
    from starlette.responses import PlainTextResponse
    if request.url.hostname not in {"localhost", "127.0.0.1", "testserver"}:
        return PlainTextResponse("Invalid host", status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def home():
    return FileResponse(ROOT / "static/index.html")


@app.get("/api/health")
async def health():
    llm_ready = False
    try:
        async with llama_client() as client:
            result = await client.get(f"http://127.0.0.1:{config['llama_port']}/health", timeout=2)
            llm_ready = result.status_code == 200
    except httpx.HTTPError:
        pass
    return {"ready": ready and llm_ready, "tts_ready": ready, "llm_ready": llm_ready,
            "error": startup_error, "styles": voice.styles, "tts_device": config["tts_device"],
            "engines": voice.catalog(), "active_engine": voice.engine}


@app.get('/api/scenario/default')
async def scenario_default():
    return default_scenario()


@app.get('/api/scenario/download')
async def scenario_download():
    return FileResponse(DEFAULT_FILE, media_type='text/markdown; charset=utf-8', filename=DEFAULT_FILE.name)


async def fit_context(client, messages, budget=None):
    return await (budget or ContextBudget()).fit(client, messages, config['context_size'],
        config['max_tokens'], config['llama_port'],
        {'Authorization': 'Bearer ' + os.environ.get('STS_LLAMA_API_KEY', '')})


async def respond(ws, message, history, scenario=None, budget=None):
    request_started = time.perf_counter()
    if not ready:
        raise ValueError(startup_error or "音声モデルを準備中です。")
    style = message.get("style", "Neutral")
    speed = float(message.get("speed", 1))
    style_weight = float(message.get("style_weight", 1.0))
    engine = message.get("engine", "sbv2")
    if engine not in ENGINES:
        raise ValueError("不明な音声モデルです。")
    speaker = message.get("speaker") or ENGINES[engine]['speakers'][0]
    if (style not in ENGINES[engine]['styles'] or speaker not in ENGINES[engine]['speakers']
            or not 0.7 <= speed <= 1.4 or not 0 <= style_weight <= 3):
        raise ValueError("音声設定が範囲外です。")
    if engine != 'sbv2' and (speed != 1 or style_weight != 1):
        raise ValueError("このモデルは速さ・スタイルの強さの調整に対応していません。")
    preview = message.get('type') == 'preview'
    if preview and (message.get('audio') or len(str(message.get('text', ''))) > 200):
        raise ValueError("試聴テキストは1〜200文字にしてください。")
    if message.get("audio"):
        if len(message["audio"]) > 5_400_000:
            raise ValueError("音声が大きすぎます。")
        wav = await asyncio.to_thread(normalize_wav, base64.b64decode(message["audio"], validate=True))
        content = [
            {"type": "text", "text": "この音声の発言に、日本語で短く返答してください。"},
            {"type": "input_audio", "input_audio": {"data": base64.b64encode(wav).decode(), "format": "wav"}},
        ]
    else:
        content = str(message.get("text", "")).strip()
        if not content or len(content) > 1000:
            raise ValueError("テキストは1〜1000文字にしてください。")
    user = {"role": "user", "content": content}
    if pipeline_lock.locked():
        await ws.send_json({"type": "status", "text": "前の処理の完了を待っています…"})
    async with pipeline_lock:
        start = request_started
        queue_seconds = time.perf_counter() - request_started
        first_token = first_audio = None
        asr_seconds = 0.0
        tts_seconds = 0.0
        audio_seconds = 0.0
        answer = buffer = ""
        await ws.send_json({"type": "status", "text": "音声を理解して返答を作っています…"})
        if isinstance(content, list):
            # Gemma's documented audio task is ASR; separate it from dialogue to
            # avoid answers that misinterpret the acoustic question as an instruction.
            content[0]["text"] = (
                "Transcribe the following speech segment in Japanese into Japanese text. "
                "Only output the transcription, with no newlines. "
                "When transcribing numbers, write the digits. Do not answer the question."
            )
            async with llama_client() as client:
                transcription_response = await client.post(
                    f"http://127.0.0.1:{config['llama_port']}/v1/chat/completions",
                    headers={"Authorization": "Bearer " + os.environ.get("STS_LLAMA_API_KEY", "")},
                    json={"model": "gemma-4-e2b", "id_slot": 0, "messages": [{"role": "user", "content": content}],
                          "temperature": 0, "max_tokens": 512, "chat_template_kwargs": {"enable_thinking": False}},
                )
                transcription_response.raise_for_status()
                transcript = transcription_response.json()["choices"][0]["message"].get("content", "").strip()
            if not transcript:
                raise ValueError("音声を認識できませんでした。もう一度話してください。")
            asr_seconds = time.perf_counter() - start
            user = {"role": "user", "content": transcript}
            await ws.send_json({"type": "transcript", "text": transcript})

        async def emit_audio(sentence):
            nonlocal first_audio, tts_seconds, audio_seconds
            if not any(character.isalnum() for character in sentence):
                return
            before = time.perf_counter()
            # Shield and finish active inference before releasing the pipeline on cancellation.
            if first_audio is None:
                await ws.send_json({'type': 'status', 'text': f"{ENGINES[engine]['name']} で音声を生成中…"})
            work = asyncio.create_task(asyncio.to_thread(voice.synthesize, sentence, style, speed, style_weight, engine, speaker))
            try:
                wav, duration = await asyncio.shield(work)
            except asyncio.CancelledError:
                await work
                raise
            tts_seconds += time.perf_counter() - before
            audio_seconds += duration
            if first_audio is None:
                first_audio = time.perf_counter() - start
            await ws.send_json({"type": "audio", "data": base64.b64encode(wav).decode(),
                                "text": sentence, "duration": duration, "engine": engine, "preview": preview,
                                "speaker": speaker, "style": style, "style_weight": style_weight, "speed": speed})

        if preview:
            await ws.send_json({'type': 'token', 'text': content})
            await emit_audio(content)
            await ws.send_json({'type': 'done', 'engine': engine, 'metrics': {
                'first_audio_s': first_audio, 'total_s': time.perf_counter() - start,
                'tts_s': tts_seconds, 'audio_s': audio_seconds}})
            return

        payload = {"model": "gemma-4-e2b", "id_slot": min(1, config.get('llama_slots', 2) - 1),
            "cache_prompt": True, "messages": [
            {"role": "system", "content": system_prompt(config["system_prompt"], scenario)}, *history, user],
            "stream": True, "max_tokens": config["max_tokens"],
            "temperature": config.get("temperature", 0.3), "top_p": 0.95, "top_k": 64,
            "chat_template_kwargs": {"enable_thinking": False}}
        async def generate(queue):
            nonlocal answer, buffer, first_token
            async with llama_client() as client:
                payload['messages'] = await fit_context(client, payload['messages'], budget)
                await receive_tokens(client, queue)
            if buffer.strip():
                await queue.put(buffer.strip())
            await queue.put(None)

        async def receive_tokens(client, queue):
            nonlocal answer, buffer, first_token
            async with client.stream("POST", f"http://127.0.0.1:{config['llama_port']}/v1/chat/completions", json=payload,
                                     headers={"Authorization": "Bearer " + os.environ.get("STS_LLAMA_API_KEY", "")}) as response:
                if response.status_code != 200:
                    detail = (await response.aread()).decode(errors="replace")[:500]
                    raise RuntimeError(f"Gemmaエラー ({response.status_code}): {detail}")
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line[6:] == "[DONE]":
                        break
                    event = json.loads(line[6:])
                    if "error" in event:
                        raise RuntimeError(str(event["error"]))
                    choices = event.get("choices") or []
                    token = choices[0].get("delta", {}).get("content") if choices else None
                    if not token:
                        continue
                    if first_token is None:
                        first_token = time.perf_counter() - start
                    answer += token
                    buffer += token
                    await ws.send_json({"type": "token", "text": token})
                    while True:
                        sentence, buffer = take_sentence(buffer, first=not emitted[0],
                            first_min=config.get('first_chunk_chars', 18),
                            max_chars=config.get('speech_chunk_chars', 80))
                        if not sentence:
                            break
                        emitted[0] = True
                        await queue.put(sentence)
        emitted = [False]
        await stream_speech(generate, emit_audio)
        if not answer.strip():
            raise RuntimeError("返答が空でした。もう一度話しかけてください。")
        history.extend([user, {"role": "assistant", "content": answer}])
        del history[:-2 * config["history_turns"]]
        await ws.send_json({"type": "done", "metrics": {
            "first_token_s": first_token, "first_audio_s": first_audio,
            "total_s": time.perf_counter() - start,
            "asr_s": asr_seconds, "tts_s": tts_seconds, "audio_s": audio_seconds,
            "prepare_queue_s": queue_seconds}})


@app.websocket("/ws")
async def conversation(ws: WebSocket):
    allowed = {f"http://localhost:{config['web_port']}", f"http://127.0.0.1:{config['web_port']}"}
    if ws.headers.get("origin") not in allowed:
        await ws.close(code=1008)
        return
    await ws.accept()
    history = []
    scenario = None
    budget = ContextBudget()
    active = None

    async def run(message):
        class TaggedSocket:
            async def send_json(self, event):
                await ws.send_json({**event, 'request_id': message.get('request_id')})
        try:
            await respond(TaggedSocket(), message, history, scenario, budget)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.exception("Conversation failed")
            await ws.send_json({"type": "error", "text": str(exc), 'request_id': message.get('request_id')})

    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > 5_500_000:
                await ws.close(code=1009)
                break
            try:
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ValueError()
            except (ValueError, TypeError):
                await ws.send_json({"type": "error", "text": "入力形式が不正です。"})
                continue
            if message.get("type") in {"cancel", "reset"}:
                if active and not active.done():
                    active.cancel()
                    await asyncio.gather(active, return_exceptions=True)
                if message["type"] == "reset":
                    history.clear()
                await ws.send_json({"type": "cancelled"})
            elif active and not active.done():
                await ws.send_json({"type": "error", "text": "返答中です。停止してから話しかけてください。"})
            elif message.get('type') == 'scenario':
                try:
                    updated = validate_scenario(message.get('scenario'))
                    scenario = updated
                    budget = ContextBudget()
                    history.clear()
                    await ws.send_json({'type': 'scenario_applied', 'scenario': scenario, 'reset': True})
                except (ValueError, UnicodeError) as exc:
                    await ws.send_json({'type': 'error', 'text': str(exc)})
            elif message.get('type') in {'message', 'preview'}:
                active = asyncio.create_task(run(message))
            else:
                await ws.send_json({'type': 'error', 'text': '不明な操作です。'})
    except WebSocketDisconnect:
        pass
    finally:
        if active and not active.done():
            active.cancel()
            await asyncio.gather(active, return_exceptions=True)
