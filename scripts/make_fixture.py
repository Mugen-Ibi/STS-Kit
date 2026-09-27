"""Generate a known spoken question directly with TTS, independently of the LLM."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sts.tts as tts
from sts.settings import settings

config = settings()
config["tts_device"] = "cpu"
tts.settings = lambda: config
voice = tts.Voice()
voice.load()
audio, seconds = voice.synthesize("日本の首都はどこですか。")
(ROOT / "run").mkdir(exist_ok=True)
(ROOT / "run/speech-question.wav").write_bytes(audio)
print(f"Known question saved ({seconds:.2f}s): 日本の首都はどこですか。")
