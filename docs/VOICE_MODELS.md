# 日本語音声モデルの比較

調査日: 2026-09-27。対象機: Windows / RTX 5070 Laptop 8GB。
CosyVoice3 0.5Bも選択肢に追加しました。[日本語処理・参照音声・実測](COSYVOICE3.md)を参照してください。
音声認識と会話の文章生成は引き続き **Gemma 4 E2B it** のみ。追加の音声LLMには完成した読み上げ文だけを渡します。

|モデル|規模・方式|日本語・制御|今回の扱い|
|---|---|---|---|
|[Qwen3-TTS 0.6B CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice)|0.6B系列、自己回帰型の音声トークン生成。コーデックなどを含む配布重みは約2.49GB|日本語を含む10言語。9話者、日本語話者はOno Anna|導入。日本語固定の読み上げ専用として使用|
|[LFM2.5-Audio 1.5B JP](https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP)|1.5B、言語バックボーンは1.2B。音声出力用デトークナイザーを併用|日本語向け音声LLM。公式の逐次TTSモードを使用|導入。会話生成・ASR機能は本アプリでは使わない|
|[Qwen3-TTS 1.7B CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice)|0.6Bより大きい同系列|日本語対応、自然言語による発話指示|調査のみ。Gemmaと8GB GPUで共存させるため小型版を優先。実機ベンチマーク未実施|
|[Kokoro 82M](https://huggingface.co/hexgrad/Kokoro-82M)|82M、StyleTTS2 / iSTFTNet系のTTS|多言語の軽量TTS|調査のみ。音声LLMではないので、今回追加する2モデルとは区別|
|[Style-Bert-VITS2 / JVNV F1](https://huggingface.co/litagin/style_bert_vits2_jvnv)|BERT + VITS系TTS|日本語、7表情、強さ0〜3、話速|既存モデルを維持。短い応答を速く返す用途の基準|

Qwen 0.6Bのモデルカードにはスタイル指示の説明もありますが、[公式推論コード](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py)は0.6Bで`instruct`を無効にします。このため本UIではQwen 0.6Bの表情・強さを無効化しています。LFMにも本アプリで対応する表情・話速パラメーターはありません。Style-Bert-VITS2だけがこれらを調整できます。

## 使い方

「音声モデル」で選び、その下の「同じ文章で聴き比べる」で「試聴する」を押します。Gemmaを呼ばずにその文章を読み上げ、音声を最大6件、ページを開いている間だけ再生欄に残します。モデルを切り替えて同じ文で繰り返すと比較できます。通常の音声会話・文字会話でも選択したモデルを使います。

モデル切り替え時は前のTTSプロセスを終了してGPUメモリを解放し、次のモデルを読み込みます。初回・切替直後は数十秒かかることがあります。同じモデルは常駐させて再利用します。生成中の「停止」は再生を止め、処理済みの音声を破棄します。現在の合成処理が終わるまで次の生成は待機します。

## ランタイム・再現

- 会話: 既存llama.cpp CUDA、Gemma Q4_0。変更なし。
- 既存TTS: `.venv` / Python 3.11 / Style-Bert-VITS2 2.5.0。
- 追加TTS: `.venv-audio` / Python 3.12 / PyTorch 2.8.0 CUDA 12.8 / Transformers 4.57.3 / qwen-tts 0.1.1 / liquid-audio 1.3.0。
- Windowsでビルド不要のPyTorch SDPAを使用。FlashAttentionは導入していません。公式モデルの機能をそのまま使うため、今回はPython実装を採用。別ランタイムより最速であるという主張ではありません。
- `setup-audio.ps1`で追加環境・重みを再構築。`requirements-audio.lock.txt`とPyTorch別指定で依存関係を固定。
- モデル固定リビジョンは`models/audio-manifest.json`。Qwen: `85e237c12c027371202489a0ec509ded67b5e4b5`、LFM: `6c34b4d590f80563f8cb2939c2ebd7686d952394`。
- 起動時はHugging Face / Transformersをオフラインに固定。録音・文章・音声を外部APIへ送信しません。

GGUF単体では今回の公式Python推論に必要な音声部品が揃わないため、音声出力を含む公式Safetensors一式を別途取得します。

## ライセンス

QwenはApache 2.0。LFMのコード・主要重みは[LFM Open License 1.0](https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP/blob/main/LICENSE)、音声部品に別ライセンスがあるため公式モデルカードも参照。JVNVモデルはCC BY-SA 4.0です。生成音声の配布でも上流の利用条件を確認してください。モデルごとの条件は同一ではありません。[出典一覧](../THIRD_PARTY_NOTICES.md)。

## 検証

以下は高速化前の追加モデル導入時の記録です。標準構成の現在の速度は[PERFORMANCE.md](PERFORMANCE.md)を参照してください。

`scripts/test_voice_api.py`は実際のWebSocketで試聴し、WAVの非無音・有限値とモデル切り替えを検査します。結果音声と計測値は`run/voice-comparison/`へ保存。`tests/test_voice_routing.py`では、試聴がGemma・会話履歴を使わないことと非対応設定の拒否を検証します。

同じ文章「こんにちは。今日はいい天気ですね。」、Gemma常駐状態での実測例:

|モデル|読み込み済みの生成時間|生成された音声の長さ|切替＋初回生成|
|---|---:|---:|---:|
|Style-Bert-VITS2|0.25秒|2.54秒|24.32秒|
|Qwen3-TTS 0.6B|9.27秒|4.24秒|35.74秒|
|LFM2.5-Audio JP|4.06秒|2.48秒|28.39秒|

少数回の実測であり、発話長、サンプリング、他アプリのGPU使用によって変わります。追加2モデルはこの公式Python実装では既存TTSより遅く、リアルタイム速度を保証しません。速度重視ならStyle-Bert-VITS2、声質比較にはQwen / LFMを選んでください。

3モデルの生成音声をGemmaで再認識し、いずれも「こんにちは。今日はいい天気ですね。」と読めることを確認しました。これはASRによる限定的な内容確認で、人の聴感評価ではありません。QwenとLFMの両方で、既知の質問音声→Gemmaの認識・回答→選択したTTSの音声出力も確認しています。

LFMはTTS専用のテキスト埋め込み経路を使い、使用しない入力音声エンコーダーとアダプターをCPUに退避しています。音声生成用のバックボーンとデトークナイザーはGPUで実行します。
