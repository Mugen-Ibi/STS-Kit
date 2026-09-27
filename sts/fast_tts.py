"""Japanese-only inference adapter for Style-Bert-VITS2 2.5.0 (AGPL-3.0).

Based on upstream models/infer.py and nlp/japanese/bert_feature.py.
Keeps the upstream phonemes, style interpolation, duration/noise and PCM normalization.
Skips the MLM head, the two unused BERT layers, and per-utterance CUDA cache eviction.
See THIRD_PARTY_NOTICES.md. No installed package is modified.
"""
import numpy as np
import torch
from transformers import DebertaV2Model

from style_bert_vits2.constants import Languages, DEFAULT_SDP_RATIO, DEFAULT_NOISE, DEFAULT_NOISEW
from style_bert_vits2.models import commons
from style_bert_vits2.models.hyper_parameters import HyperParameters
from style_bert_vits2.models.infer import get_net_g
from style_bert_vits2.nlp import clean_text, cleaned_text_to_sequence, bert_models
from style_bert_vits2.nlp.japanese.g2p import text_to_sep_kata

from .settings import VOICE, BERT


class FastJapaneseModel:
    def __init__(self, device, bert_precision='float32'):
        self.device = device
        self.hps = HyperParameters.load_from_json(VOICE / 'config.json')
        if not self.hps.version.endswith('JP-Extra'):
            raise ValueError('The fast adapter requires a JP-Extra model.')
        self.style2id = self.hps.data.style2id
        self.styles = torch.from_numpy(np.load(VOICE / 'style_vectors.npy')).to(device)
        self.net = get_net_g(str(VOICE / 'jvnv-F1-jp_e160_s14000.safetensors'),
                             self.hps.version, device, self.hps)
        # Eval weights are immutable: fold legacy weight normalization once at startup.
        for module in self.net.modules():
            if hasattr(module, 'weight_g'):
                torch.nn.utils.remove_weight_norm(module)
        self.bert = DebertaV2Model.from_pretrained(str(BERT)).eval()
        # Upstream consumes hidden_states[-3] (22 of 24 layers), not the final output.
        self.bert.encoder.layer = self.bert.encoder.layer[:-2]
        if self.bert.z_steps > 1:
            raise ValueError('Unsupported DeBERTa refinement steps.')
        dtype = torch.float16 if bert_precision == 'float16' and device.startswith('cuda') else torch.float32
        self.bert.to(device=device, dtype=dtype)
        self.tokenizer = bert_models.load_tokenizer(Languages.JP, str(BERT))
        self.sid = torch.zeros(1, dtype=torch.long, device=device)

    def features(self, text, word2ph):
        text = ''.join(text_to_sep_kata(text, raise_yomi_error=False)[0])
        if len(word2ph) != len(text) + 2:
            raise ValueError('Japanese text/phoneme alignment failed.')
        inputs = self.tokenizer(text, return_tensors='pt').to(self.device)
        # Bypass DebertaV2Model.forward, which always retains every hidden state.
        mask = inputs['attention_mask']
        embedding = self.bert.embeddings(input_ids=inputs['input_ids'], mask=mask)
        hidden = self.bert.encoder(embedding, mask, output_hidden_states=False,
                                   return_dict=True).last_hidden_state[0]
        counts = torch.tensor(word2ph, device=self.device)
        return torch.repeat_interleave(hidden, counts, dim=0, output_size=sum(word2ph)).T.float()

    @torch.inference_mode()
    def infer(self, text, language=Languages.JP, style='Neutral', style_weight=1.0,
              length=1.0, line_split=False):
        if language != Languages.JP or line_split:
            raise ValueError('The fast adapter accepts unsplit Japanese text only.')
        norm, phone, tone, counts = clean_text(text, Languages.JP, use_jp_extra=True, raise_yomi_error=False)
        phone, tone, language_ids = cleaned_text_to_sequence(phone, tone, Languages.JP)
        if self.hps.data.add_blank:
            phone, tone, language_ids = [commons.intersperse(values, 0) for values in (phone, tone, language_ids)]
            counts = [count * 2 for count in counts]
            counts[0] += 1
        bert = self.features(norm, counts).unsqueeze(0)
        if bert.shape[-1] != len(phone):
            raise ValueError('Japanese BERT/phoneme alignment failed.')
        phone, tone, language_ids = [torch.tensor(values, dtype=torch.long, device=self.device).unsqueeze(0)
                                     for values in (phone, tone, language_ids)]
        lengths = torch.tensor([phone.shape[-1]], device=self.device)
        mean = self.styles[0]
        vector = mean + (self.styles[self.style2id[style]] - mean) * style_weight
        output = self.net.infer(phone, lengths, self.sid, tone, language_ids, bert,
            style_vec=vector.unsqueeze(0), sdp_ratio=DEFAULT_SDP_RATIO, noise_scale=DEFAULT_NOISE,
            noise_scale_w=DEFAULT_NOISEW, length_scale=length)
        samples = output[0][0, 0].float().cpu().numpy()
        peak = float(np.max(np.abs(samples)))
        if not np.isfinite(samples).all() or peak < 1e-8:
            raise RuntimeError('音声生成に失敗しました。')
        samples = (samples / peak * 32767).astype(np.int16)
        return self.hps.data.sampling_rate, samples
