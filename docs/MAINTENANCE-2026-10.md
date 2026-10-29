# 2026-10-29 保守検証

公開版 `fb50b480a6982acd05a76c028471da31f38a7b20` を起点にした保守です。既存のモデル、音声精度、UI、Windowsセットアップの構成は維持しました。未公開の `feature/tailscale-remote` は対象にしていません。

## 修正

- 配列・オブジェクトなど不正なWebSocket操作名、および深すぎるJSONを、接続を失わずエラーとして返す。JSONテキスト以外のバイナリフレームは1003で明示的に切断する。
- 最初の音声区切りでも `speech_chunk_chars` を超える遠い読点を選ばない。通常の早出しと文字の保持を回帰テストで確認。
- `verify_voice_readback.py` に必要な `type: message` を追加。文字起こし後のキャンセル確認もモデルなしでテスト。
- localhostへ接続する全6診断クライアントで `proxy=None` を明示。環境変数のプロキシへ音声を送ることを防ぐ。
- WebSockets 17.3、FileLock 4.2.4、CosyVoice環境のPillow 13.0.0へ更新。certifi / aiohttp / Brotli / msgpack / Hydra等の修正リリースを反映。Hugging Face Hubの既存推移依存 `hf-xet` もロックに記載。
- GitHub Actionsを公式v7リリースのSHAへ固定。Node.js 26 LTS、Windows / Linux × Python 3.11 / 3.12でモデル不要テストを実行する設定に更新。

## 実行した検証と限界

LinuxのPython 3.11.17 / 3.12.14でPythonテスト52件成功。Node.js 24.19.0 / 26.13.0で音声クライアントテスト3件成功。Python構文検査、Ruffの実行時エラー関連規則（E9/F63/F7/F82）、公開ファイル監査、差分空白検査も成功。新しい回帰テストを旧コードへ適用すると7件失敗し、修正対象を再現しました。

実際のUvicornとWebSockets 17を一時的なloopbackポートで接続し、不正入力・深すぎるJSONの後の復帰、reset・cancel、バイナリフレームの1003切断を確認しました。この試験はモデルのlifespanを明示的に無効にします。FileLock 4と既存Hugging Face HubのロックAPI、Pillow 13等の最小API試験も成功しています。

3ロックファイルは、別指定のtorch / torchaudio 2.8.0を含め、対象のWindows / Python版で依存解決を検証しました。**Windowsでのインストール、CUDA、実モデル合成、実マイク、声質・性能比較、リモートCIは今回未実行**です。Linuxのモデル不要テスト成功を、Linuxでの推論対応や実モデル互換性の保証とはしません。`compare_tts.py`・`verify_roleplay.py`・`benchmark.py`は対応機で再実行が必要です。

## 残っている依存リスク

`pip-audit 2.10.1` / PyPI情報でロックを監査しました。パッケージ名とadvisory IDの組を重複排除すると、基本環境22→9、追加音声73→48、CosyVoice98→34。3環境全体では102→75です。同一問題の別IDは統合していないため、独立した脆弱性の件数ではありません。別指定のtorch 2.8.0にも8件の報告（重複を含む）があり、**安全性監査の全件解消ではありません**。

|保留|理由と次の検証|
|---|---|
|追加音声のTransformers / Accelerate|最新版qwen-tts 0.1.1が `transformers==4.57.3` / `accelerate==1.12.0` を要求。上流対応または互換性を検証した別構成が必要|
|追加音声のPillow 13|Gradio 6.17.3、および確認時点の最新版6.31.0も `pillow<13` を要求。13への強制更新は依存解決に失敗したため不採用|
|基本・CosyVoiceのTransformers 5 / NumPy 2 / 新PyTorch等|日本語高速アダプター、固定CosyVoiceコード、Python・CUDA・GPU条件を含むモデル同等性検証が必要。未検証の一括更新はしない|
|Setuptools 81以上|既存の辞書・ビルド互換性制約 `<81` を保持。78.1.0から80.10.2への部分更新では新しいadvisoryは残る|
|CosyVoiceのDiffusers / Lightning / ModelScope / PyArrow等|古い固定依存に既知報告が残る。上流固定コードと実モデルを含む移行が必要|

通常の推論は固定リビジョンのローカルモデルを使い、インターネット待受やモデルの自由なアップロードは提供していません。これにより一部advisoryの前提は限定されますが、未対応問題を安全と断定するものではありません。信頼できないモデル設定・重みを読み込まず、localhost運用を維持してください。

## 依存の一次情報

- [WebSockets 17変更点](https://websockets.readthedocs.io/en/stable/project/changelog.html)（Python 3.11以上、使っているasyncio APIは維持）
- [FileLock変更履歴](https://py-filelock.readthedocs.io/en/latest/changelog.html)
- [Pillow 13変更点](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)
- [qwen-tts配布メタデータ](https://pypi.org/pypi/qwen-tts/0.1.1/json)
- [Gradio配布メタデータ](https://pypi.org/pypi/gradio/6.31.0/json)
- [Node.jsリリース状況](https://nodejs.org/en/about/previous-releases)
