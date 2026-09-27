"""Download official inference assets and pin their source revision."""
import json
import os
from pathlib import Path
import truststore
truststore.inject_into_ssl()
ROOT = Path(__file__).resolve().parents[1]
os.environ['HF_HOME'] = str(ROOT / '.cache/huggingface')
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '30'
os.environ.pop('HF_HUB_OFFLINE', None)
from huggingface_hub import HfApi, snapshot_download
repo = 'FunAudioLLM/Fun-CosyVoice3-0.5B-2512'
manifest_file = ROOT / 'models/audio-manifest.json'
manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
revision = '29e01c4e8d000f4bcd70751be16fa94bf3d85a18'
info = HfApi().model_info(repo, revision=revision, files_metadata=True)
print(repo, revision, [(f.rfilename, f.size) for f in info.siblings], flush=True)
snapshot_download(repo, revision=revision, local_dir=ROOT / 'models/cosyvoice3',
    allow_patterns=['*.json', '*.yaml', '*.pt', 'campplus.onnx', 'speech_tokenizer_v3.onnx',
                    'CosyVoice-BlankEN/*', 'README.md', 'LICENSE*'],
    ignore_patterns=['*rl*', '*.zip', '*.plan', '*estimator*'], max_workers=3)
manifest[repo] = {'revision': revision, 'folder': 'cosyvoice3'}
manifest_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
