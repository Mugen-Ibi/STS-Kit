"""CosyVoice3 adapter with synthetic Japanese prompt and offline local assets."""
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from .settings import ROOT


class CosyVoice:
    def __init__(self):
        import pyopenjtalk
        import torch
        source = ROOT / '.venv/Lib/site-packages/pyopenjtalk/open_jtalk_dic_utf_8-1.11'
        destination = Path(tempfile.gettempdir()) / 'sts-kit-jtalk-1.11'
        if not (destination / 'sys.dic').exists():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        pyopenjtalk.OPEN_JTALK_DICT_DIR = str(destination).encode('utf-8')
        self.kana = lambda text: pyopenjtalk.g2p(text, kana=True)
        code = ROOT / 'vendor/CosyVoice'
        sys.path[:0] = [str(code), str(code / 'third_party/Matcha-TTS')]
        from cosyvoice.cli.cosyvoice import CosyVoice3
        logging.getLogger().setLevel(logging.ERROR)
        self.folder = ROOT / 'models/cosyvoice3'
        self.model = CosyVoice3(str(self.folder), load_trt=False, load_vllm=False, fp16=torch.cuda.is_available())
        if torch.cuda.is_available():
            # Upstream fp16 enables autocast but keeps FP32 resident weights.
            # Store the speech LM itself in FP16 to fit alongside Gemma on 8GB.
            self.model.model.llm.half()
            torch.cuda.empty_cache()
        reference = json.loads((self.folder / 'reference.json').read_text(encoding='utf-8'))
        prompt = 'You are a helpful assistant.<|endofprompt|>' + self.kana(reference['text'])
        self.model.add_zero_shot_spk(prompt, str(self.folder / 'reference.wav'), 'jvnv-f1')
        # Reference features are now cached. The ~1GB ONNX speech encoder is no
        # longer needed for text-only requests with this fixed synthetic speaker.
        del self.model.frontend.speech_tokenizer_session
        del self.model.frontend.campplus_session

    def synthesize(self, text):
        import torch
        parts = [item['tts_speech'].float().cpu() for item in self.model.inference_zero_shot(
            self.kana(text), '', '', zero_shot_spk_id='jvnv-f1', stream=False, text_frontend=False)]
        if not parts:
            raise RuntimeError('CosyVoice3の音声出力が空でした。')
        return torch.cat(parts, dim=1).numpy().reshape(-1), self.model.sample_rate
