"""Create a synthetic Japanese reference; no personal recording is used."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sts import tts
folder = ROOT / 'models/cosyvoice3'
folder.mkdir(parents=True, exist_ok=True)
path = folder / 'reference.wav'
text = 'こんにちは。今日はいい天気ですね。あなたとお話しできるのを楽しみにしています。'
if not path.exists():
    config = tts.settings()
    tts.settings = lambda: {**config, 'tts_device': 'cpu'}
    voice = tts.Voice()
    voice.load()
    wav, duration = voice.synthesize(text)
    path.write_bytes(wav)
    print(f'Created synthetic reference: {duration:.2f}s', flush=True)
(folder / 'reference.json').write_text(json.dumps({
    'text': text, 'source': 'litagin/style_bert_vits2_jvnv / JVNV F1 JP-Extra',
    'license': 'CC BY-SA 4.0', 'synthetic': True,
    'url': 'https://huggingface.co/litagin/style_bert_vits2_jvnv'}, ensure_ascii=False, indent=2), encoding='utf-8')
