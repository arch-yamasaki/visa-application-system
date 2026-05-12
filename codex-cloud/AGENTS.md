# codex-cloud

Codex CLIをCloud Run Jobs上で実行するリモート実行基盤。

## ディレクトリ構成

```text
codex-cloud/
  orchestrator/
    main.py            # FastAPI アプリ (Cloud Run Service)
    Dockerfile
    requirements.txt
    static/index.html  # Web UI
  runner/
    entrypoint.sh      # codex exec ラッパー
    Dockerfile
    requirements.txt
    gcs_helper.py      # GCS アップロード/ダウンロード
    update_status.py   # Firestore 状態更新
    PREINSTALLED_LIBS.md
  frontend/
    index.html         # orchestrator/static/ と同一内容
  docs/
```

## コンポーネント

### orchestrator/ — FastAPI (Cloud Run Service)
セッション管理、Cloud Run Jobの起動、結果配信を行うAPIサーバー。Port 8080。
- `POST /sessions`: プロンプト受付 → GCS保存 → Job起動
- `GET /sessions/{id}/result`: 最終出力の取得
- `GET /sessions/{id}/files`: ワークスペース内ファイルの閲覧・ダウンロード

### runner/ — Cloud Run Jobs
codex exec を隔離環境で実行し、成果物をGCS/Firestoreに書き戻すバッチジョブ。
- Node 22 (Codex CLI) + Python 3 (GCPクライアント)
- `--sandbox workspace-write` でサンドボックス実行
- ワークスペースは `tar.zst` で圧縮してGCSに保存

### frontend/ — Web UI
プロンプト入力、ステータスポーリング、結果表示の単一HTMLページ。

## 重要ファイル

- `docs/README.md`: 実行基盤のアーキテクチャ概要、3方式の比較
- `docs/option3_codex_exec_json_cloud_run_jobs.md`: 採用方式の詳細設計
- `orchestrator/main.py`: API全エンドポイント定義
- `runner/entrypoint.sh`: ジョブ実行フロー（認証→プロンプト取得→codex実行→成果物アップロード）

## GCPリソース

| リソース | 値 |
|---|---|
| GCS Bucket | `visa-codex-mvp-data` |
| GCP Project | `visa-codex-mvp` |
| Region | `asia-northeast1` |
| Firestore Collection | `sessions` |
| Cloud Run Job | `codex-runner-job` |
