import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def settings():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"
    if local.exists():
        config.update(json.loads(local.read_text(encoding="utf-8")))
    config['llama_server'] = os.environ.get('STS_LLAMA_SERVER', config['llama_server'])
    return config


def resolve_llama_server(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file():
        return path.resolve()
    executable = shutil.which(value)
    if executable:
        return Path(executable).resolve()
    raise FileNotFoundError('llama-serverが見つかりません。runtime/llamaに配置するか、config.local.jsonのllama_serverを指定してください。')


GEMMA = ROOT / "models/gemma/gemma-4-E2B-it-Q4_0.gguf"
PROJECTOR = ROOT / "models/gemma/mmproj-gemma-4-E2B-it-Q8_0.gguf"
VOICE = ROOT / "models/voices/jvnv-F1-jp"
BERT = ROOT / "models/bert"
