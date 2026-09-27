import io
import threading
import os
import shutil
import tempfile
import sys
from pathlib import Path

import soundfile as sf

from .settings import BERT, VOICE, settings


class Voice:
    def __init__(self):
        self.lock = threading.Lock()
        self.model = None
        self.styles = ["Neutral"]

    def load(self):
        import pyopenjtalk
        dictionary = Path(pyopenjtalk.__file__).parent / "open_jtalk_dic_utf_8-1.11"
        if not (dictionary / "sys.dic").is_file():
            raise RuntimeError("OpenJTalk辞書がありません。setup.ps1を実行してください。")
        if os.name == "nt" and not str(dictionary).isascii():
            # OpenJTalk's native Windows fopen cannot open UTF-8 Japanese paths.
            destination = Path(tempfile.gettempdir()) / "sts-kit-jtalk-1.11"
            if not str(destination).isascii():
                raise RuntimeError("TEMPを英数字のパスに設定してください。OpenJTalk辞書で必要です。")
            if not (destination / "sys.dic").exists():
                shutil.copytree(dictionary, destination, dirs_exist_ok=True)
            dictionary = destination
        pyopenjtalk.OPEN_JTALK_DICT_DIR = str(dictionary).encode("utf-8")
        import torch
        from style_bert_vits2.logging import logger
        logger.remove()
        logger.add(sys.stderr, level="WARNING", diagnose=False, backtrace=False)
        from style_bert_vits2.constants import Languages
        from style_bert_vits2.nlp import bert_models
        from style_bert_vits2.tts_model import TTSModel

        config = settings()
        torch.set_num_threads(config["tts_threads"])
        if config.get('tts_fast', True):
            from .fast_tts import FastJapaneseModel
            self.model = FastJapaneseModel(config['tts_device'], config.get('tts_bert_precision', 'float32'))
        else:
            bert_models.load_model(Languages.JP, str(BERT))
            bert_models.load_tokenizer(Languages.JP, str(BERT))
            self.model = TTSModel(
                model_path=VOICE / "jvnv-F1-jp_e160_s14000.safetensors",
                config_path=VOICE / "config.json",
                style_vec_path=VOICE / "style_vectors.npy",
                device=config["tts_device"],
            )
            self.model.load()
        self.styles = list(self.model.style2id)

    def synthesize(self, text, style="Neutral", speed=1.0, style_weight=1.0):
        with self.lock:
            if self.model is None:
                raise RuntimeError("音声モデルを準備中です。")
            from style_bert_vits2.constants import Languages
            rate, samples = self.model.infer(
                text=text, language=Languages.JP, style=style, style_weight=style_weight,
                length=1.0 / speed, line_split=False,
            )
            out = io.BytesIO()
            sf.write(out, samples, rate, format="WAV", subtype="PCM_16")
            return out.getvalue(), len(samples) / rate
