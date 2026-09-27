"""Fallback for a stalled large-file transfer; validate every range and full SHA256."""
import concurrent.futures
import hashlib
import os
from pathlib import Path
import time
import requests
import truststore
truststore.inject_into_ssl()
ROOT = Path(__file__).resolve().parents[1]
SIZE = 2940723992
SHA = '71f2726a3607aad8613c25a7e3417f8dcc4e1ae398984a97bc481268ac1b4578'
URL = 'https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP/resolve/6c34b4d590f80563f8cb2939c2ebd7686d952394/model.safetensors'
target = ROOT / 'models/lfm-audio-jp/model.safetensors'
partial = target.with_suffix('.download')
with partial.open('wb') as f:
    f.truncate(SIZE)
CHUNK = 32 * 1024 * 1024
def download(start):
    end = min(start + CHUNK, SIZE) - 1
    for attempt in range(4):
        try:
            with requests.get(URL + f'?download=true&part={start}', headers={'Range': f'bytes={start}-{end}'},
                              stream=True, timeout=(20, 30)) as response:
                response.raise_for_status()
                if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{SIZE}':
                    raise RuntimeError('Unexpected download byte range')
                with partial.open('r+b') as f:
                    f.seek(start)
                    count = 0
                    for data in response.iter_content(1024 * 1024):
                        count += len(data)
                        if count > end-start+1:
                            raise RuntimeError('Oversized range')
                        f.write(data)
                    if count != end-start+1:
                        raise RuntimeError('Incomplete range')
            return count
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1 + attempt)
done = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    jobs = [pool.submit(download, start) for start in range(0, SIZE, CHUNK)]
    for job in concurrent.futures.as_completed(jobs):
        done += job.result()
        print(f'{done / SIZE:.0%}', flush=True)
with partial.open('rb') as f:
    actual = hashlib.file_digest(f, 'sha256').hexdigest()
if actual != SHA:
    raise RuntimeError('SHA256 mismatch')
os.replace(partial, target)
print('LFM model SHA256 verified.', flush=True)
