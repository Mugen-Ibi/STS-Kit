# 自宅ホストと会場のクライアント

対象は自分が管理する会場クライアント1台から自宅の推論を使う運用です。
既存の FastAPI + WebSocket プロトコルをそのまま使い、依存パッケージは追加しません。
既定の localhost 運用は変更ありません。ブラウザ音声入力には HTTPS が必要なので、
Tailscale IP の HTTP へ直接接続せず、Tailscale Serve の HTTPS/WSS を使います。

```text
会場ブラウザ / 自作クライアント (Tailscale)
  -> https / wss :443 (tailnet 内だけ)
  -> 自宅 Tailscale Serve -> http://127.0.0.1:8765
  -> STS API -> loopback llama.cpp / ローカル音声モデル
```

## 設定

既存の `config.local.json` に次のキーを追加してください（ファイル全体を上書きしない）。
ホスト名は自宅 PC の実際の MagicDNS FQDN に置き換えます。

```json
{
  "remote_enabled": true,
  "remote_origin": "https://home.example-tailnet.ts.net",
  "remote_request_timeout_s": 180
}
```

`remote_enabled` の既定は false。`remote_origin` はパス・ポート・末尾スラッシュなしの
正確な HTTPS ts.net origin です。ワイルドカードは使えません。
`remote_request_timeout_s` は待ち行列を含む1応答の期限（10〜600秒、既定180秒）。

起動プロセスの環境変数 `STS_REMOTE_TOKEN` に、暗号学的にランダムな32バイト以上に由来する
URL-safe トークン（32〜256文字、英数字・`_`・`-`）を渡します。
これは Tailscale のデバイス登録キーではなく STS 専用の秘密です。
この手順はトークンを生成しません。安全な作成・受け渡し方法を別途決め、値を
コマンド履歴・URL・設定JSON・ログ・Gitへ残さないでください。共有端末に保存しないでください。
環境は通常の起動プロセスから子プロセスへ継承されるため、自宅ホストのプロセスも信頼境界です。
起動は通常の `python launch.py --no-browser` と同じです。設定やトークンが不正なら
モデル起動前に失敗します。遠隔モードでは自動でブラウザを開きません。

## Tailscale 設定（明示承認後に手動実施）

以下は説明であり、実装・テストでは実行しません。デバイス登録、HTTPS有効化、
Serve、tailnet の grants/ACL、ファイアウォール、永続認証を変更する際は、対象と変更内容を
1操作ずつ確認してください。Funnel、ルーターのポート転送、0.0.0.0 待受は使いません。

1. 自宅 PC と会場クライアントが同じ tailnet に参加済みか確認。
2. 自宅の443だけをそのクライアントから許可する最小限の grants/ACL を検討。
   tailnet の既定の許可範囲を、アプリの認証だけで限定できると思わないでください。
3. `tailscale serve status` と `tailscale funnel status` で既存の構成を確認。公開転送がないことを確認し、他用途の構成を上書きしない。HTTPSの同意画面がFunnelの許可も含む場合は、そのまま承認せず設定内容を確認。
4. 自宅 PC で承認済みの場合に限り、前景で次を実行。

   ```powershell
   tailscale serve --https=443 http://127.0.0.1:8765
   ```

   HTTPS の有効化を求められた場合は、それを別の設定変更として確認します。
   TLS 証明書の取得でホスト名が証明書透明性ログに現れる点も確認してください。
   前景の Serve は終了時に停止します。`--bg` の永続化はこの手順に含めません。
5. 会場の管理下クライアントから設定した HTTPS URL を開き、トークンで接続。
   自宅からUIを使う場合も同じ HTTPS URL を使用します。

STS と llama.cpp は127.0.0.1のまま。ServeがTLSを終端します。
アプリは転送されたHost/Originと秘密を検証し、Tailscaleのユーザーヘッダーを認証として信用しません。
`X-Forwarded-*` は認証バイパスになりません。遠隔モードではlocalhostのHTTPにもBearerが必要です。
Tailscaleをインストールしただけでアプリが外部到達可能になるわけではありません。

## クライアントとプロトコル

ブラウザは最初に `/` のログイン画面を表示します。トークンはメモリ中の入力から
`POST /api/session` の Authorization ヘッダーで送信し、localStorageやURLに保存しません。
成功時の署名付きCookieは Secure / HttpOnly / SameSite=Strict / host-only。
新しいHTTP/WS接続で12時間後に失効し、アプリ再起動でも失効します。
期限切れ・再起動後は再ログインしてください。既存WSはその接続の終了まで有効です。
イベント終了時はSTSを停止し、トークンを破棄・ローテーションして起動環境から除去してください。
単一の信頼された利用者向けで、ユーザーごとの権限やアカウント管理はありません。複数タブでも履歴は接続ごとに分離しますが、推論は既存のGPUロックで直列化されるため、会場では1クライアント・1タブを推奨します。

自作の電話クライアントは `GET /api/health` と `wss://<host>/ws` のハンドシェイクに
`Authorization: Bearer <token>` を付けます。Originは省略可能ですが、送る場合は設定値と一致が必要です。
ブラウザのCookie接続は正確なOrigin必須。URLクエリでの認証は受け付けません。
TLS検証を無効にしないでください。全HTTP API・静的ファイル・WSが認証対象です。

既存の送信例（秘密情報なし）:

```json
{"type":"message","text":"こんにちは","request_id":1}
```

音声は `text` の代わりに `audio` にbase64 WAVを設定（WAVは4MB以下・28秒以内）。
`token`、`audio`（base64 WAVと文）、`done` が逐次到着します。
`request_id` が一致するイベントだけを再生してください。
`cancel` は現在の応答を止め、`reset` は履歴も消去します。完了通知は `cancelled`。
`ping` には `pong` が返ります。再接続時の会話履歴は新規になり、入力の自動再送はしません。
ブラウザは世界設定を再適用します。黒電話のフックやUSB音声機器の制御は既存クライアント側の責務で、
この変更は専用ハードウェアのドライバーを追加しません。

## 切断・診断と事前リハーサル

ブラウザは15秒間隔のpingと45秒の応答監視で切断を検出し、再生・録音を止めます。
サーバーも20秒間隔のWebSocket ping/pongを使用します。ブラウザの背景タブや端末休止では
タイマーが遅れることがあるため、会場では前面表示・電源管理を確認してください。
切断時は応答をキャンセルし、再接続は2秒後に開始します。送信の自動リプレイはしません。
健康確認には10秒のクライアント期限があります。
推論の期限切れもキャンセル扱いですが、実行中の同期TTSは安全に完了するまで待ってから
共有モデルのロックを解放します。このため停止通知は設定した期限を超えることがあります。

認証済み `/api/health` は `ready`、`llm_ready`、`tts_ready`、`remote_enabled`、`transport` を返します。
リモート応答には内部例外の本文を含めません。モデル起動失敗は自宅側ログで診断します。
401は認証、403はHost/Origin、到達不能はTailscale/Serve/名前解決、ready=falseはモデルを切り分けてください。
このhealthはtailnet疎通や会場のマイクを検査するものではありません。

本番前に別ネットワークからテキスト、承認済みの合成WAV、キャンセル、回線断・再接続、
トークン失効を確認してください。実マイクの録音は別途明示許可がある場合だけ実施します。
約2日・20時間のイベントでは12時間の再ログインと休憩時の回線・PC温度・電源を計画し、
実ネットワークで待ち時間を測定してください。DERP経由の場合の遅延もあり、性能保証はしません。
ローカルへ戻す際は承認されたServe停止と `remote_enabled: false`、STS再起動を行います。
遠隔モードを無効にする前にServeを停止し、意図しない転送を残さないでください。

## 根拠と検証範囲

2026-10-22に公式資料を確認:
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)
- [Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)

Serveはtailnet内限定、Funnelは公開用です。HTTPSはtailnet側での有効化と証明書が必要です。
この変更の自動テストはモデルなしのASGI・模擬音声・ブラウザJSであり、
実Tailscale、別ネットワーク、GPU推論、黒電話の動作確認とは区別します。
