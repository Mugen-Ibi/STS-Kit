"""Download only inference assets; pin resolved revisions in models/manifest.json."""
import json
import os
from pathlib import Path

import truststore
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / ".cache/huggingface")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ.pop("HF_HUB_OFFLINE", None)
from huggingface_hub import HfApi, snapshot_download

SOURCES = [
    ("ggml-org/gemma-4-E2B-it-GGUF", "b4243c156154b6dca9324415f8c7ccc098b4aed1", "gemma",
     ["gemma-4-E2B-it-Q4_0.gguf", "mmproj-gemma-4-E2B-it-Q8_0.gguf", "README.md"]),
    ("litagin/style_bert_vits2_jvnv", "205830ca1d49e666ddfbf2a755f0108e9cade4dd", "voices",
     ["jvnv-F1-jp/*", "README.md"]),
    ("ku-nlp/deberta-v2-large-japanese-char-wwm", "547b0e8b044fba3f9b84d0ab9f990440bd130c8b", "bert",
     ["*.json", "*.txt", "*.model", "pytorch_model.bin", "README.md"]),
]


def main():
    manifest_path = ROOT / "models/manifest.json"
    manifest_path.parent.mkdir(exist_ok=True)
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = {}
    for repo, revision, folder, patterns in SOURCES:
        revision = revision or old.get(repo, {}).get("revision") or HfApi().model_info(repo).sha
        print(f"Downloading {repo}@{revision}", flush=True)
        snapshot_download(repo, revision=revision, local_dir=ROOT / "models" / folder,
                          allow_patterns=patterns, max_workers=3)
        manifest[repo] = {"revision": revision, "folder": folder, "patterns": patterns}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("All inference models are ready.", flush=True)


if __name__ == "__main__":
    main()
