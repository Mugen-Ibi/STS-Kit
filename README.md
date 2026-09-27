# STS Kit — 2030年からの電話

Windowsで動く、日本語のローカル音声対話・ロールプレイアプリです。2026年のユーザーと2030年の日本に暮らす人物が、電話越しに会話する設定を同梱しています。架空の歴史をMarkdownで差し替えられます。

音声認識と返答生成は **Gemma 4 E2B it**、標準の読み上げは **Style-Bert-VITS2 / JVNV F1 JP-Extra**。初回導入後の推論にクラウドAPIは不要です。モデルの重み・実行環境・録音はこのリポジトリに含みません。

## できること

- マイク、WAV、文字から会話。返答を生成しながら短い区切りで読み上げます。
- 発話後の無音で自動送信。待ちは350 / 600 / 1000msから選択でき、ボタン操作で送ることもできます。
- 7種類の声の表情、スタイルの強さ、話速の調整。
- 架空史Markdownの読み込み・本文確認・ブラウザへの保存・通常会話への切り替え。
- Qwen3-TTS / LFM2.5-Audio JP / CosyVoice3の追加導入と比較試聴。速度を重視した標準構成はStyle-Bertです。

**発話終了後に認識する方式です。** 常時接続で話しながら認識する完全な双方向ストリーミングではありません。自動送信の待ち600ms、認識・生成、ブラウザや出力機器の遅延が合計の待ち時間になります。[実測と制約](docs/PERFORMANCE.md)を参照してください。

## 必要な環境

- Windows x64。検証機はWindows / Ryzen 7 260 / RTX 5070 Laptop 8GB。
- CUDA対応のNVIDIA GPUと対応ドライバー。基本構成を8GB VRAMで検証。CPUへの切り替えは可能ですが、低遅延の対象外です。
- Git、[uv](https://docs.astral.sh/uv/getting-started/installation/)、モデル取得用のネット接続。
- Gemma 4の音声入力に対応する[llama.cpp](https://github.com/ggml-org/llama.cpp/releases)。検証版は[b10964](https://github.com/ggml-org/llama.cpp/releases/tag/b10964)。
- モデル、PyTorch、ダウンロードキャッシュ用に十分な空き容量（基本構成でも30GB程度の余裕を推奨）。追加音声モデルは別途容量を使います。

Linux / macOS / AMD GPUでの起動手順は未検証です。Python仮想環境はセットアップが作成します。

## 導入

```powershell
git clone https://github.com/Mugen-Ibi/STS-Kit.git
cd STS-Kit
```

1. llama.cppのWindows CUDA版を取得し、`llama-server.exe`と必要なDLLを`runtime/llama/`へまとめて配置します。GPU・ドライバーに合う配布を選んでください。
2. 既存のllama.cppを使う場合は`config.local.example.json`を`config.local.json`としてコピーし、`llama_server`を実際のパスに変更します。環境変数`STS_LLAMA_SERVER`でも指定できます。
3. PowerShellでセットアップを実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

セットアップは依存パッケージ・Gemma GGUFと音声入力用mmproj・JVNV F1・日本語BERT・OpenJTalk辞書を取得します。重みのリビジョンは固定しています。モデルごとの[利用条件](THIRD_PARTY_NOTICES.md)を確認してください。

4. `Start-STS.cmd`をダブルクリックします。準備後にブラウザが開きます。すでに起動中なら[ローカル画面](http://127.0.0.1:8765/)を開いてください。
5. 終了時は`Stop-STS.cmd`。管理下のプロセスだけを照合して停止します。

## 会話する

「話す」で録音開始。自動送信を有効にしている場合、発話後の無音で送信されます。間を取りながら話したい場合は自動送信をオフにして、もう一度「送信する」を押します。ヘッドホンを推奨します。

標準の人物は「朝倉灯」。まず「もしもし、そちらは何年ですか？」と話しかけてください。[架空史の原稿](scenarios/japan-2030.md)は創作であり、実際のニュースや予測ではありません。[歴史の編集方法](docs/ROLEPLAY.md)も参照してください。

- 「未来人と話す」をオフにすると通常会話。
- 「停止」は生成・再生を停止。実行中のTTS処理が終わるまで次の処理は待つ場合があります。
- 「新しい会話」は世界設定を残して履歴をリセット。
- 「同じ文章で聴き比べる」はLLMを通さず、入力文をそのまま読み上げます。
- スタイルの強さは0〜3。Neutralでは変化しません。HappyやSadなどを選んで調整します。

入力は文字1000文字、音声0.15〜28秒、WAV最大4MB。世界設定はUTF-8の`.md`、4000文字・16KBまでです。

## 設定・追加モデル

共有の既定値は`config.json`。個別の変更はGit対象外の`config.local.json`に記述し、再起動してください。[設定一覧・トラブル対処](docs/SETUP.md)を用意しています。

```powershell
# 任意。標準のStyle-Bertだけなら不要
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-audio.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-cosy.ps1
```

[追加モデルの比較](docs/VOICE_MODELS.md) / [CosyVoice3の構成](docs/COSYVOICE3.md)

## 開発・検証

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/audio_client.test.cjs
# アプリ起動後。合成した質問音声と結果をrun/へ保存します
.\.venv\Scripts\python.exe -X utf8 scripts/verify_roleplay.py
.\.venv\Scripts\python.exe -X utf8 scripts/benchmark.py --rounds 7
```

Node.jsはブラウザ音声処理のテストにだけ使い、アプリ実行には不要です。モデル不要のテスト環境は[CONTRIBUTING.md](CONTRIBUTING.md)、構造は[ARCHITECTURE.md](docs/ARCHITECTURE.md)、レビュー結果は[REVIEW.md](docs/REVIEW.md)を参照してください。

## 公開範囲・ライセンス

このソースは[GNU AGPL v3](LICENSE)。モデル・辞書・依存ライブラリには別の条件があります。[第三者の著作物と出典](THIRD_PARTY_NOTICES.md)を参照してください。

アプリはlocalhost専用です。公開リポジトリであることと、アプリをインターネットに公開できることは別です。`models/`、`runtime/`、仮想環境、`config.local.json`、`.env`、`logs/`、`run/`はGit対象外です。通常操作の録音・会話をファイルに保存しませんが、インポートした歴史はブラウザに残ります。[保存範囲・セキュリティ](SECURITY.md)を確認してください。

## English overview

Local Japanese speech-to-speech and fictional roleplay on Windows. Gemma 4 E2B it handles ASR and dialogue; Style-Bert-VITS2 generates speech. Import a UTF-8 Markdown world, talk to a fictional person in 2030, or disable roleplay for ordinary conversation. Model weights are downloaded separately. The tested platform is Windows with an NVIDIA 8GB GPU; other platforms are not validated. This is turn-based speech with incremental reply playback, not full-duplex streaming. Source license: AGPL v3; model licenses are separate.
