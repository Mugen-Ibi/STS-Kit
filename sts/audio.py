import io
import math
import re

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

MAX_AUDIO_SECONDS = 28
MAX_AUDIO_BYTES = 4_000_000


def normalize_wav(data: bytes) -> bytes:
    if len(data) > MAX_AUDIO_BYTES:
        raise ValueError("音声ファイルが大きすぎます。28秒以内で録音してください。")
    try:
        with sf.SoundFile(io.BytesIO(data)) as source:
            if source.format != "WAV" or source.channels > 2 or not 8000 <= source.samplerate <= 96000:
                raise ValueError("8〜96kHz、モノラルまたはステレオのWAVを指定してください。")
            if not 0.15 <= source.frames / source.samplerate <= MAX_AUDIO_SECONDS:
                raise ValueError("音声の長さは0.15〜28秒にしてください。")
            rate = source.samplerate
            samples = source.read(dtype="float32", always_2d=True).mean(axis=1)
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise ValueError("WAV音声を読み込めませんでした。") from exc
    if not np.isfinite(samples).all() or np.max(np.abs(samples)) < 0.001:
        raise ValueError("音声が無音です。マイクの入力を確認してください。")
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        samples = resample_poly(samples, 16000 // divisor, rate // divisor)
    output = io.BytesIO()
    sf.write(output, np.clip(samples, -1, 1), 16000, format="WAV", subtype="PCM_16")
    return output.getvalue()


def take_sentence(buffer: str, final=False, *, first=False, first_min=18, max_chars=100):
    match = re.search(r"[。！？!?\n]", buffer)
    if first:
        clause = next((m for m in re.finditer(r'[、，,：:]', buffer) if m.end() >= first_min), None)
        if clause and (not match or clause.end() < match.end()):
            return buffer[:clause.end()].strip(), buffer[clause.end():]
    if match and match.end() <= max_chars:
        end = match.end()
    elif len(buffer) >= max_chars:
        end = buffer.rfind("、", 15, max_chars) + 1 or max_chars
    elif final:
        end = len(buffer)
    else:
        return "", buffer
    return buffer[:end].strip(), buffer[end:]
