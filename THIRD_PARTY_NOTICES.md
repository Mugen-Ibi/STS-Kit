# 第三者の著作物・モデル・ライセンス

確認日: 2026-09-27。STS Kitのソースは[GNU AGPL v3](LICENSE)で提供します。モデル、辞書、ライブラリの条件をこのライセンスへ変更するものではありません。重みとランタイムはリポジトリに同梱せず、利用者のPCへ別途取得します。

## 基本構成

|対象|出典・条件|用途|
|---|---|---|
|Style-Bert-VITS2 2.5.0|[litagin02/Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2)、AGPL-3.0（上流の一部部品には別条件あり）|日本語音声合成|
|JVNV F1 JP-Extra|[litagin/style_bert_vits2_jvnv](https://huggingface.co/litagin/style_bert_vits2_jvnv)、CC BY-SA 4.0|音声モデル|
|JVNVコーパス|[JVNV corpus](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvnv_corpus)、CC BY-SA 4.0|上記モデルの学習音声の出典|
|日本語DeBERTa|[ku-nlp/deberta-v2-large-japanese-char-wwm](https://huggingface.co/ku-nlp/deberta-v2-large-japanese-char-wwm)、CC BY-SA 4.0|音声合成のテキスト特徴|
|Gemma 4 E2B it|[Google DeepMindのモデルカード](https://huggingface.co/google/gemma-4-E2B-it)、Apache 2.0|音声認識と会話生成|
|Gemma GGUF / mmproj|[ggml-org/gemma-4-E2B-it-GGUF](https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF)|上記モデルの量子化配布|
|llama.cpp|[ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)、MIT|Gemmaの実行環境|

JVNVモデルの条件は[上流のモデル利用条件](https://github.com/litagin02/Style-Bert-VITS2/blob/master/docs/TERMS_OF_USE.md)に記載されています。上流文書では開発者の「お願い」とライセンスを区別しています。別の音声モデルの条件をJVNVへ流用しないでください。生成音声を公開・配布する際も、使用したモデル・音声素材の条件を確認してください。

JVNV利用の出典表記例: `JVNVコーパス / litagin Style-Bert-VITS2 JVNV F1 (CC BY-SA 4.0)`。BERTの配布元は京都大学言語メディア処理研究室です。コード、モデル、生成物を一律に同じライセンスだと扱わないでください。

## 高速化アダプターの出典

`sts/fast_tts.py`は上流Style-Bert-VITS2 2.5.0の`models/infer.py`、`nlp/japanese/bert_feature.py`、`tts_model.py`の推論方法を基にした日本語用アダプターです。上流と同じ音素処理、スタイル補間、推論パラメーター、PCM正規化を使用します。変更点は未使用計算の省略、GPU上の特徴量展開、weight normalizationの事前計算、CUDA領域の再利用です。AGPL v3で配布し、上流の帰属を維持します。

日本語BERTの旧形式重みは`weights_only=True`で読み、safetensorsへ変換します。通常設定では重みを量子化せず、モデルのコピーを公開リポジトリへ追加しません。

## 任意の追加モデル

|対象|配布元・条件|
|---|---|
|Qwen3-TTS 0.6B CustomVoice|[Qwen公式モデル](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice)、Apache 2.0|
|LFM2.5-Audio 1.5B JP|[LiquidAI公式モデル](https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP)、[LFM Open License 1.0](https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP/blob/main/LICENSE)。音声部品の条件もモデルカードを参照|
|CosyVoice3 0.5B|[Fun-CosyVoice3-0.5B-2512](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)、Apache 2.0|
|CosyVoiceコード / Matcha-TTS|[公式リポジトリとサブモジュール](https://github.com/QwenAudio/CosyVoice)のLICENSEを参照。配布元から別途取得|

CosyVoice用の参照音声はJVNV F1でローカル生成し、由来を`models/cosyvoice3/reference.json`に記録します。個人の録音や参照音声自体をリポジトリに同梱しません。

## 依存・辞書

Python依存のバージョンは`requirements*.lock.txt`に記録しています。PyTorch、Transformers、FastAPI、NumPy、SciPy、SoundFile、PyOpenJTalkなどの条件は各配布物のLICENSE/COPYINGに従います。特にOpenJTalk・MeCab・辞書は部品ごとの条件を確認してください。NVIDIAランタイムはNVIDIAの配布条件に従い、Gitへ追加しません。
