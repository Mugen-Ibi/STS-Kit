"""Optional local sweep; does not change app settings."""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import torch
from sts.tts import Voice

voice = Voice()
voice.load()
rows = []
for threads in (1, 2, 4, 6):
    torch.set_num_threads(threads)
    for precision in ('highest', 'high'):
        torch.set_float32_matmul_precision(precision)
        samples = []
        for step in range(9):
            torch.manual_seed(2026)
            start = time.perf_counter()
            with torch.inference_mode():
                voice.synthesize('2027年の夏は、商店街で麦茶を配っていました。')
            if step >= 2:
                samples.append(time.perf_counter() - start)
        rows.append(dict(threads=threads, precision=precision, median_s=statistics.median(samples)))
        print(rows[-1], flush=True)
(ROOT / 'run/tts-tuning.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
