"""Opt-in real-model equivalence/latency check for the pinned SBV2 adapter."""
import gc
import io
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sts.tts as tts
from sts.fast_tts import FastJapaneseModel


def main():
    original = tts.settings
    tts.settings = lambda: {**original(), 'tts_fast': False}
    voice = tts.Voice()
    voice.load()
    text = '2027年の夏は、商店街で麦茶を配っていました。'
    results, reference = {}, {}
    def synth(model, style):
        torch.manual_seed(2026)
        with torch.inference_mode():
            rate, samples = model.infer(text=text, style=style, style_weight=1.8, line_split=False)
        return rate, samples
    for name in ['upstream', 'fast_float32', 'fast_float16']:
        model = voice.model if name == 'upstream' else FastJapaneseModel('cuda', name.split('_')[1])
        for _ in range(2):
            synth(model, 'Neutral')
        timings = []
        for _ in range(7):
            start = time.perf_counter()
            synth(model, 'Neutral')
            timings.append(time.perf_counter() - start)
        record = {'median_s': statistics.median(timings), 'styles': {}}
        for style in voice.styles:
            rate, samples = synth(model, style)
            assert np.isfinite(samples).all() and np.max(np.abs(samples.astype(float))) > 10
            if name == 'upstream':
                reference[style] = samples
            ref = reference[style]
            same_length = len(ref) == len(samples)
            rms = float(np.sqrt(np.mean((samples.astype(float) - ref.astype(float)) ** 2))) / 32768 if same_length else None
            record['styles'][style] = dict(seconds=len(samples) / rate, same_length=same_length, waveform_rms_difference=rms)
            if name == 'fast_float32':
                assert same_length and rms < .001, (style, record['styles'][style])
            folder = ROOT / 'run/tts-optimization'
            folder.mkdir(exist_ok=True)
            sf.write(folder / f'{name}-{style}.wav', samples, rate)
        results[name] = record
        print(name, record['median_s'], flush=True)
        if name != 'upstream':
            del model
            gc.collect()
            torch.cuda.empty_cache()
    (ROOT / 'run/tts-optimization/results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
