"""Convert the upstream legacy torch archive to safe, memory-mapped weights."""
from pathlib import Path
import torch
from safetensors.torch import save_file

root = Path(__file__).resolve().parents[1] / "models/bert"
target = root / "model.safetensors"
if not target.exists():
    print("Converting BERT to safetensors...", flush=True)
    weights = torch.load(root / "pytorch_model.bin", map_location="cpu", weights_only=True, mmap=True)
    print(f"Loaded {len(weights)} tensors", flush=True)
    # This checkpoint shares one flat storage; saving contiguous tensor views does not duplicate it.
    temporary = target.with_suffix(".safetensors.tmp")
    save_file({key: value.contiguous() for key, value in weights.items()}, str(temporary), metadata={"format": "pt"})
    temporary.replace(target)
    print("BERT conversion complete.", flush=True)

import truststore
truststore.inject_into_ssl()
import pyopenjtalk
dictionary = Path(pyopenjtalk.__file__).parent / "open_jtalk_dic_utf_8-1.11"
if not (dictionary / "sys.dic").is_file():
    pyopenjtalk._extract_dic()
print("OpenJTalk dictionary ready.", flush=True)
