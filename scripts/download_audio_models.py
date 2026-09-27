"""Install official TTS assets, retaining resolved revisions for repeatable setup."""
import json
import os
from pathlib import Path
import truststore
truststore.inject_into_ssl()
ROOT = Path(__file__).resolve().parents[1]
os.environ['HF_HOME'] = str(ROOT / '.cache/huggingface')
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '30')
os.environ.pop('HF_HUB_OFFLINE', None)
from huggingface_hub import HfApi, snapshot_download

manifest_file = ROOT / 'models/audio-manifest.json'
manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
for repo, folder, revision in [
    ('Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', 'qwen3-tts', '85e237c12c027371202489a0ec509ded67b5e4b5'),
    ('LiquidAI/LFM2.5-Audio-1.5B-JP', 'lfm-audio-jp', '6c34b4d590f80563f8cb2939c2ebd7686d952394')]:
    info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    print(repo, revision, [(x.rfilename, x.size) for x in info.siblings], flush=True)
    snapshot_download(repo, revision=revision, local_dir=ROOT / 'models' / folder,
                      ignore_patterns=['*.wav', '*.mp3', '*.mp4', '*.png', '*.jpg', '.gitattributes'], max_workers=3)
    manifest[repo] = {'revision': revision, 'folder': folder}
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
