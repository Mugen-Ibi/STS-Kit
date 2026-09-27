import io

import numpy as np
import pytest
import soundfile as sf

from sts.audio import normalize_wav, take_sentence


def wav(seconds=1, rate=48000, channels=1, silent=False):
    samples = np.zeros(int(seconds * rate)) if silent else 0.2 * np.sin(2 * np.pi * 440 * np.arange(int(seconds * rate)) / rate)
    if channels == 2:
        samples = np.column_stack([samples, samples])
    out = io.BytesIO()
    sf.write(out, samples, rate, format="WAV")
    return out.getvalue()


def test_normalize_stereo_and_resample():
    data = normalize_wav(wav(channels=2))
    samples, rate = sf.read(io.BytesIO(data))
    assert rate == 16000
    assert samples.shape == (16000,)
    assert np.max(samples) > 0.1


@pytest.mark.parametrize("data", [b"not audio", wav(silent=True), wav(seconds=0.1), wav(seconds=29, rate=16000)], ids=["invalid", "silence", "short", "long"])
def test_reject_invalid_audio(data):
    with pytest.raises(ValueError):
        normalize_wav(data)


def test_sentence_boundaries_and_tail():
    first, tail = take_sentence("こんにちは。今日は晴れです。")
    assert (first, tail) == ("こんにちは。", "今日は晴れです。")
    assert take_sentence("途中") == ("", "途中")
    assert take_sentence("残り", final=True) == ("残り", "")
    assert len(take_sentence("あ" * 120)[0]) <= 100
