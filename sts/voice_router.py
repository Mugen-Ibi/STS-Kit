"""One persistent, isolated TTS worker at a time; switching releases CUDA memory."""
import atexit
import base64
import json
import os
import queue
import subprocess
import sys
import threading
from .settings import ROOT

STYLES = ['Neutral', 'Angry', 'Disgust', 'Fear', 'Happy', 'Sad', 'Surprise']
ENGINES = {
    'sbv2': dict(name='Style-Bert-VITS2 · JVNV F1', styles=STYLES, speakers=['JVNV F1'],
                 description='日本語専用。表情・強さ・速さを調整できます。', folder='voices/jvnv-F1-jp'),
    'qwen3': dict(name='Qwen3-TTS 0.6B · CustomVoice', styles=['Neutral'],
                  speakers=['ono_anna', 'aiden', 'ryan', 'vivian', 'serena', 'uncle_fu', 'dylan', 'eric', 'sohee'],
                  description='日本語は Ono Anna 推奨。9話者。0.6B版は表情指示に非対応。', folder='qwen3-tts'),
    'lfm': dict(name='LFM2.5-Audio 1.5B JP', styles=['Neutral'], speakers=['標準'],
                description='日本語音声LLMの読み上げモード。話者・表情は固定です。', folder='lfm-audio-jp'),
    'cosy3': dict(name='CosyVoice3 0.5B', styles=['Neutral'], speakers=['JVNV F1 参照'],
                  description='日本語の合成参照音声（JVNV F1）を使います。漢字は読みへ自動変換。表情・強さ・速さは本UIでは固定です。',
                  folder='cosyvoice3'),
}


class VoiceRouter:
    styles = STYLES

    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.engine = None
        self.log = None
        atexit.register(self.close)

    def catalog(self):
        manifest_path = ROOT / 'models/audio-manifest.json'
        installed = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        complete_folders = {x['folder'] for x in installed.values()}
        return [dict(id=k, **v, available=(ROOT / 'models' / v['folder'] / 'config.json').exists()
                     and (k == 'sbv2' or (v['folder'] in complete_folders and
                          (ROOT / ('.venv-cosy/Scripts/python.exe' if k == 'cosy3' else '.venv-audio/Scripts/python.exe')).exists()
                          and (k != 'cosy3' or ((ROOT / 'models/cosyvoice3/reference.wav').exists()
                              and (ROOT / 'vendor/CosyVoice/cosyvoice/cli/cosyvoice.py').exists()))))) for k, v in ENGINES.items()]

    def close(self):
        process, self.process = self.process, None
        self.engine = None
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdin.close()
            process.stdout.close()
        if self.log:
            self.log.close()
            self.log = None

    def load(self):
        with self.lock:
            self._switch('sbv2')

    def _switch(self, engine):
        if engine == self.engine and self.process and self.process.poll() is None:
            return
        self.close()
        python = sys.executable if engine == 'sbv2' else str(ROOT / '.venv-audio/Scripts/python.exe')
        if engine == 'cosy3':
            python = str(ROOT / '.venv-cosy/Scripts/python.exe')
        self.log = open(ROOT / 'logs' / f'tts-{engine}.log', 'w', encoding='utf-8')
        self.process = subprocess.Popen([python, '-X', 'utf8', '-u', '-m', 'sts.voice_worker', engine],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            text=True, encoding='utf-8', env={**os.environ, 'PYTHONUTF8': '1'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.responses = queue.Queue()
        def read_lines(process, responses):
            try:
                for line in process.stdout:
                    responses.put(line)
            finally:
                responses.put(None)
        threading.Thread(target=read_lines, args=(self.process, self.responses), daemon=True).start()
        result = self._receive()
        if not result.get('ready'):
            raise RuntimeError('音声モデルを起動できませんでした。')
        self.engine = engine

    def _receive(self):
        try:
            line = self.responses.get(timeout=240)
            if line is None:
                raise RuntimeError('音声プロセスが終了しました。logs/tts-*.logを確認してください。')
            result = json.loads(line)
            if result.get('error'):
                raise RuntimeError(result['error'])
            return result
        except Exception:
            self.close()
            raise

    def synthesize(self, text, style='Neutral', speed=1.0, style_weight=1.0, engine='sbv2', speaker=None):
        if engine not in ENGINES:
            raise ValueError('不明な音声モデルです。')
        speaker = speaker or ENGINES[engine]['speakers'][0]
        if speaker not in ENGINES[engine]['speakers'] or style not in ENGINES[engine]['styles']:
            raise ValueError('音声モデルに対応していない設定です。')
        with self.lock:
            self._switch(engine)
            self.process.stdin.write(json.dumps(dict(text=text, style=style, speed=speed,
                style_weight=style_weight, speaker=speaker), ensure_ascii=False) + '\n')
            self.process.stdin.flush()
            result = self._receive()
            return base64.b64decode(result['audio']), result['duration']
