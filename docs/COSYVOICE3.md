# CosyVoice3 0.5B

公式[Fun-CosyVoice3-0.5B-2512](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)を4つ目の音声モデルとして追加。音声認識・返答の文章生成はGemma 4 E2Bのままです。

「音声モデル」→「CosyVoice3 0.5B」を選んで「試聴する」、または通常の会話を送信します。切り替え時には前のTTSプロセスを終了してGPUメモリを解放します。読み込み済みのモデルは再利用します。

## 声と日本語処理

参照音声はJVNV F1 JP-Extraを使ってローカル生成した約5.6秒の合成音声です。個人の録音を使用しません。現在の話者は「JVNV F1 参照」の1種類で、モデル自身の固定話者ではありません。参照の文章・出典・ライセンスは`models/cosyvoice3/reference.json`に記録しています。

[公式の日本語サンプル](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/example.py)に従い、入力と参照文をOpenJTalkでカタカナの読みに変換します。画面には元の漢字かな交じり文を表示します。固有名詞などの読みが誤る場合は、試聴欄に読みを直接入力してください。中国語・英語用のテキスト正規化は無効にしています。

本UIでは表情・強さ・速さは固定です。CosyVoice自体の全機能を公開しているわけではありません。

## 実行環境

- 専用`.venv-cosy` / Python 3.12 / PyTorch 2.8.0 CUDA 12.8 / Transformers 4.51.3。
- 公式コード: `QwenAudio/CosyVoice`、コミット`074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`。
- Matcha-TTS: 公式サブモジュール固定コミット`dd9105b34bf2be2230f4aa1e4769fb586a3c824e`。
- モデル固定リビジョン: `29e01c4e8d000f4bcd70751be16fa94bf3d85a18`。
- 音声生成はCUDA、音声LMはFP16で保持。参照特徴をCPU版ONNX Runtimeで一度計算し、ONNXセッションを解放して特徴のみ再利用します。
- TensorRT / vLLMは使用しません。Windowsで既存Gemmaと共存させた構成です。
- 推論はオフライン。Whisperパッケージは参照音声のメル特徴計算にだけ使用し、Whisperの認識モデルはダウンロード・実行しません。

再構築は既存の`setup.ps1`に続けて`setup-cosy.ps1`を実行します。依存は`requirements-cosy.lock.txt`、PyTorchは別指定。重みは約5.4GBで、別途ランタイムとキャッシュの空き容量が必要です。

## 本機での動作確認（2026-09-27）

RTX 5070 Laptop 8GB、Gemma 4 E2Bを同時実行した状態で測定しました。文章・生成される音声の長さ・他のGPU処理によって変動します。

- 「こんにちは。今日はいい天気ですね。」: 切り替え後の初回38.16秒、読み込み済み2.97秒（音声3.00秒）。画面からの試聴でも4.12秒で生成できました。
- 音声入力から「日本の首都は東京です。」と答える会話: 最初の音声まで2.26秒、うち音声生成1.94秒。
- 音声LMをFP16で保持した後のGPU全体使用量は約6.2GB、空き約1.6GBでした。
- 生成音声の再認識結果: 「こんにちは。今日はいい天気ですね。」と一致（空白・句読点を除く）。これは読み上げ内容の確認であり、主観的な声質評価ではありません。
- 自動テスト16件成功。SBV2からの切り替え、試聴API、通常の文字・音声会話、ブラウザの選択と試聴を確認しました。

測定結果と音声は`run/voice-comparison/`、会話結果は`run/smoke-results-cosy3.json`に保存しています。

## ライセンス

CosyVoiceコード・モデルはApache 2.0。参照はlitagin公開のJVNV F1由来の合成音声（CC BY-SA 4.0）です。参照音声・出力の扱いは[JVNVの利用条件](https://github.com/litagin02/Style-Bert-VITS2/blob/master/docs/TERMS_OF_USE.md)も確認してください。
