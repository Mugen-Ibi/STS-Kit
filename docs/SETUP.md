# 導入・設定・トラブル対処

最初の手順は[README](../README.md)。PowerShellの例はリポジトリ直下で実行します。

## 実行環境

|用途|環境|
|---|---|
|アプリ・Style-Bert|`.venv` / Python 3.11 / PyTorch 2.8.0 CUDA 12.8|
|Qwen / LFM（任意）|`.venv-audio` / Python 3.12|
|CosyVoice（任意）|`.venv-cosy` / Python 3.12 / 公式コードを`vendor/`へ取得|
|Gemma|別プロセスのllama.cpp CUDA / Q4_0 + mmproj Q8_0|

Pythonの依存は各`requirements*.lock.txt`で固定し、PyTorchは別指定で入れます。llama.cppのCUDAランタイムとPyTorchのCUDAランタイムは別配布です。llama.cppのDLL一式を残してください。CUDA Toolkit自体の導入は標準手順に含みません。

`runtime/llama/llama-server.exe`、`config.local.json`のパス、または環境変数`STS_LLAMA_SERVER`で実行ファイルを指定します。PATH上の`llama-server.exe`も指定可能です。相対パスはリポジトリ直下を基準に解決します。

## 主な設定

`config.local.json`には変更項目だけを書きます。値はアプリ再起動後に反映します。

|項目|既定値|意味|
|---|---:|---|
|`web_port` / `llama_port`|8765 / 18181|localhostの待受ポート|
|`context_size`|8192|1スロット当たりの文脈上限|
|`llama_slots`|2|0を音声認識、1を会話に割当。1なら同じスロットを共有|
|`llama_cache_ram_mb`|0|llama.cppの追加RAMプロンプトキャッシュを無効。スロット内KVは再利用|
|`gpu_layers`|99|llama.cppにGPU配置を指示|
|`tts_device`|`cuda`|`cpu`へ変更可能。ただし速度は別途測定が必要|
|`tts_threads`|2|音声ワーカーのCPUスレッド数|
|`tts_fast`|true|Style-Bertの日本語専用高速化。falseで上流の推論へ戻す|
|`tts_bert_precision`|`float32`|高速経路のBERT精度。float16は省メモリ比較用、標準では使わない|
|`first_chunk_chars`|18|最初の音声を読点で早出しする最低文字数|
|`speech_chunk_chars`|80|通常の音声区切りの上限目安|
|`max_tokens`|180|1返答の生成上限|
|`history_turns`|2|保持する直近の往復数|
|`temperature`|0.3|会話の生成温度|
|`system_prompt`|日本語の短い返答|通常会話用。ロールプレイは世界設定と専用指示を使用|

短すぎる音声区切りはイントネーションが不自然になり、合成回数も増えます。小さい値ほど常に速いわけではありません。`tts_fast`は同梱のJP-Extra用です。別の音声モデルを使う際はアダプターの互換性を確認してください。

## よくある問題

- **llama-serverが見つからない**: `config.local.example.json`を参考にパスを指定。`setup.ps1`はllama.cpp本体を取得しません。
- **Gemmaのアーキテクチャや音声を認識しない**: Gemma 4音声入力に対応するllama.cppを使用。検証版はb10964です。
- **CUDAのエラー / メモリ不足**: 他のGPUアプリを閉じる、`llama_slots: 1`を試す、TTSをCPUに変更。モデルを切り替える際は読み込み待ちが発生します。
- **辞書・日本語パスのエラー**: `setup.ps1`を再実行。OpenJTalk辞書は必要に応じてASCIIのTEMP配下にコピーします。TEMPパス自体が非ASCIIの場合は書き込み可能なASCIIパスを指定してください。
- **マイクが使えない**: Chrome / Edgeでlocalhostを開き、サイトのマイク許可と入力機器を確認。アプリ内ブラウザの制限がある場合は通常のブラウザを使用。
- **言い終わる前に送信される**: 無音待ちを長めにするか、自動送信をオフ。待ちは350 / 600 / 1000msから選べます。無音判定は簡易的な音量判定で、雑音や話し方により誤判定があります。
- **設定を変えたのに会話が変わらない**: 表示されたファイル名とモードを確認。試聴は世界設定を使いません。
- **ポート使用中**: `Stop-STS.cmd`で以前のインスタンスを終了してから起動。無関係なプロセスは自動停止しません。
- **ダウンロードに失敗**: 回線・プロキシ・証明書を確認。TLS検証は無効にしないでください。セットアップにはネット接続が必要です。

バグ報告はOS、GPU、llama.cppの版、使用モデル、再現手順を含めてください。ログを添付する前に[SECURITY.md](../SECURITY.md)の保存範囲を確認してください。
