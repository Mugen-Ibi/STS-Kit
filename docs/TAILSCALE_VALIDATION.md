# Tailscale遠隔モードの検証記録

2026-10-22、Windowsの既存チェックアウト、feature/tailscale-remote。
変更前はmainでclean。originは `https://github.com/Mugen-Ibi/STS-Kit.git` と確認。

## 実施

- `.venv-test/Scripts/python.exe -m pytest -q -p no:cacheprovider`: 48件成功。
  元の音声・シナリオ・パイプライン・ルーティング検証と、remote設定のfail-closed、
  HTTP/WS認証、Host/Origin、Cookie属性・期限・改ざん・再起動失効、転送ヘッダー偽装、
  ping、cancel、切断、タイムアウト、例外の秘匿、健康確認、接続間の履歴分離を含む。
- `node --test tests/audio_client.test.cjs`: 4件成功。
  PCM、録音ワークレットのflush、WSS URLと古い応答の破棄、heartbeat切断時の停止を確認。
- `.venv/Scripts/python.exe scripts/test_remote_loopback.py`: 成功。
  実際の127.0.0.1上の一時ポートでHTTP認証とWS、メモリ内の合成WAV、
  ping、キャンセル、切断後の応答タスク終了を確認。推論は模擬。
- `scripts/check_public.py`: 成功（完全な秘密情報・依存監査を意味しない）。
- `git diff --check`: 成功。

既存Starlette TestClientからhttpxに関する非推奨警告1件あり。テスト失敗ではなく、
今回のための依存変更はしていません。既存pytestキャッシュの書き込み権限警告を避けるため、
最終実行ではキャッシュプラグインを無効化しました。権限設定は変更していません。

## 未実施

実Tailscale Serve・証明書/TLS終端・tailnet ACL・異なるネットワーク間の疎通、
GPU/モデル推論、マイク録音、黒電話ハードウェア、20時間の連続運転は未検証。
自動テストは実会場の性能や安定性を保証しません。

VPN/ファイアウォール/公開転送/デバイス登録は変更せず、実認証情報も生成・保存していません。
実運用には、対象PC・既存Serve構成・正確なFQDN・アクセス許可範囲を確認してから、
認証情報の作成・受け渡しとServe/HTTPS/ACLの必要な変更をそれぞれ明示承認してください。
設定手順と切り分けは[TAILSCALE.md](TAILSCALE.md)。
