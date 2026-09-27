# 開発への参加

Windows / Python 3.11を基本構成とします。変更の目的、再現手順、検証結果をIssueまたはPRに記載してください。個人の録音・会話・ローカルパス・トークンは含めないでください。

## モデルなしでテスト

```powershell
uv venv --python 3.11 .venv-test
uv pip install --python .venv-test/Scripts/python.exe -r requirements-test.txt
.\.venv-test\Scripts\python.exe -m pytest -q
node --test tests/audio_client.test.cjs
python scripts/check_public.py
```

Node.js 22でブラウザ音声処理をテストできます。モデルのダウンロードやGPUは不要です。GitHub Actionsでもこの範囲を実行します。

## モデルを使う変更

音声生成、文分割、文脈処理を変える場合は、セットアップ後に`verify_roleplay.py`と`benchmark.py`を実行し、音声内容と待ち時間を確認してください。Style-Bertアダプターを変える場合は`compare_tts.py`で上流との比較ができます。この比較は大きなモデルを複数ロードするため、通常のアプリを止めてから実行します。

ベンチマークにはOS・GPU・ランタイム版・文・測定回数・中央値・ばらつき・計測開始と終了の定義を添えます。サーバーの生成時間をマイクからスピーカーまでの遅延と呼ばないでください。モデルの精度を下げる変更は速度だけで採用しません。

## PR前の確認

- PythonテストとNodeテスト、`git diff --check`が通る。
- 入力検証、停止、切り替え、オフライン推論を維持する。
- 新しい設定には既定値・説明・既存利用者の移行手順がある。
- モデル、録音、`.env`、個別設定、ログ、キャッシュを追加していない。
- 依存するコード・モデルの出典とライセンスを記載する。

コードは既存の[LICENSE](LICENSE)の条件で扱います。モデルの重みをPRへ含めないでください。
