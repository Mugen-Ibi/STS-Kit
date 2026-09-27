"""Private stdin/stdout JSON protocol. Model diagnostics go only to stderr."""
import base64
import io
import json
import sys
import traceback
from .settings import ROOT, settings


def main():
    protocol = sys.stdout
    sys.stdout = sys.stderr
    def reply(message):
        protocol.write(json.dumps(message, ensure_ascii=False) + '\n')
        protocol.flush()
    try:
        import torch
        import soundfile as sf
        import numpy as np
        torch.set_num_threads(settings()['tts_threads'])
        engine = sys.argv[1]
        device = settings()['tts_device']
        if engine == 'sbv2':
            from .tts import Voice
            model = Voice()
            model.load()
        elif engine == 'qwen3':
            from qwen_tts import Qwen3TTSModel
            model = Qwen3TTSModel.from_pretrained(str(ROOT / 'models/qwen3-tts'),
                device_map=device, dtype=torch.bfloat16 if device == 'cuda' else torch.float32,
                attn_implementation='sdpa')
        elif engine == 'cosy3':
            from .cosy_voice import CosyVoice
            model = CosyVoice()
        elif engine == 'lfm':
            from liquid_audio import LFM2AudioModel, LFM2AudioProcessor, ChatState
            class TextOnlyLFM(LFM2AudioModel):
                def _prefill(self, *, text, audio_in, audio_in_lens, audio_out, modality_flag):
                    # This worker only accepts text. In upstream _prefill, the
                    # all-text case is exactly these embeddings plus empty audio slots.
                    if audio_in.numel() or audio_out.numel() or audio_in_lens.numel():
                        raise ValueError('This worker only supports TTS text input.')
                    return self.lfm.embed_tokens(text)
            path = ROOT / 'models/lfm-audio-jp'
            processor = LFM2AudioProcessor.from_pretrained(path, device=device).eval()
            model = TextOnlyLFM.from_pretrained(path, device=device).eval()
            # ASR stays with Gemma; these LFM input-audio modules are never used.
            model.conformer.to('cpu')
            model.audio_adapter.to('cpu')
            if device == 'cuda':
                torch.cuda.empty_cache()
        else:
            raise ValueError('Unknown TTS engine')
        reply({'ready': True})
        for line in sys.stdin:
            try:
                request = json.loads(line)
                text = request['text']
                with torch.inference_mode():
                    if engine == 'sbv2':
                        wav, duration = model.synthesize(text, request['style'], request['speed'], request['style_weight'])
                    else:
                        if engine == 'qwen3':
                            waves, rate = model.generate_custom_voice(text=text, language='Japanese',
                                speaker=request['speaker'], max_new_tokens=512)
                            samples = waves[0]
                        elif engine == 'cosy3':
                            samples, rate = model.synthesize(text)
                        else:
                            chat = ChatState(processor)
                            chat.new_turn('system')
                            chat.add_text('Perform TTS in japanese.')
                            chat.end_turn()
                            chat.new_turn('user')
                            chat.add_text(text)
                            chat.end_turn()
                            chat.new_turn('assistant')
                            codes = []
                            ended = False
                            for token in model.generate_sequential(**chat, max_new_tokens=512,
                                    audio_temperature=0.8, audio_top_k=64):
                                if token.numel() > 1:
                                    if (token >= 2048).any():
                                        ended = True
                                        break
                                    codes.append(token)
                            if not codes:
                                raise RuntimeError('音声トークンを生成できませんでした。')
                            if not ended:
                                raise RuntimeError('音声生成の上限に達しました。文章を短くして試してください。')
                            samples = processor.decode(torch.stack(codes, 1).unsqueeze(0)).float().cpu().numpy().reshape(-1)
                            rate = 24000
                        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
                        if not samples.size or not np.isfinite(samples).all():
                            raise RuntimeError('音声生成に失敗しました。')
                        out = io.BytesIO()
                        sf.write(out, samples, rate, format='WAV', subtype='PCM_16')
                        wav, duration = out.getvalue(), len(samples) / rate
                reply({'audio': base64.b64encode(wav).decode(), 'duration': duration})
            except Exception as exc:
                traceback.print_exc()
                reply({'error': f'{type(exc).__name__}: {exc}'})
    except Exception as exc:
        traceback.print_exc()
        reply({'error': f'{type(exc).__name__}: {exc}'})


if __name__ == '__main__':
    main()
