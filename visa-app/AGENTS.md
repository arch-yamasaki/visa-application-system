# visa-app

ビザ申請書類のレビュー支援アプリケーション。

## 構成

- `frontend/` — React 19 + Vite。ケース管理、ドキュメントレビュー、PDFハイライト表示。
- `backend/` — FastAPI + Uvicorn。抽出エンジン（Gemini同期/Codex非同期）、GCS/Firestore管理。
- `jobs/codex-runner/` — Cloud Run Job。Codex CLI非同期実行コンテナ。

## 開発

```bash
# ターミナル1: フロントエンド
cd frontend && npm run dev        # localhost:5173

# ターミナル2: バックエンド
cd backend && uvicorn main:app --reload --port 8080
```

frontend の Vite proxy が `/api/*` を `localhost:8080` に転送する。

## 本番環境でのAPIアクセス

本番（Cloud Run）ではフロントエンドとバックエンドが同一コンテナで動作する。フロントエンドは開発時と同様に `/api/*` プレフィックス付きでAPIを呼ぶ。`StripApiPrefixMiddleware`（backend/main.py）が `/api/` プレフィックスを除去し、FastAPIのルート（`/cases/...` 等）にリライトする。

Chrome拡張（rasens-autofill）はバックエンドAPIに直接 `/cases/...` でアクセスするため、ミドルウェアを経由しない。

## 抽出エンジン

| エンジン | 方式 | 用途 |
|---|---|---|
| Gemini | 同期。PDF/テキスト→Gemini API→構造化JSON | 通常の申請書類抽出 |
| Codex | 非同期。Cloud Run Job→codex exec→結果収穫 | 複雑な分析・統合処理 |

## autofill連携

- `backend/autofill_adapter.py` — 現行Gemini抽出結果をChrome拡張が扱いやすい case_data 風JSONへ寄せる互換アダプタ。canonical `case_data` 整備後は削除・縮小候補。
- `GET /cases/{case_id}/autofill-data` — 現行Chrome拡張（rasens-autofill）が呼び出すエンドポイント。将来的には backend が `application_data` rows を生成して返すAPIへ寄せ、Chrome拡張側のマッピング責務を薄くする。

## デプロイ

Dockerfileはマルチステージビルドで、frontendビルド成果物をbackendコンテナに統合する。

```bash
# ローカルビルド確認
docker build -t visa-app .

# Cloud Run デプロイ
gcloud run deploy visa-app \
  --source . \
  --region asia-northeast1 \
  --project visa-codex-mvp
```

### Secret Manager

`GOOGLE_API_KEY`（Gemini API用）は GCP Secret Manager で管理し、Cloud Run の環境変数としてマウントしている。

| シークレット名 | 用途 | レプリケーション |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API 認証キー | `asia-northeast1`（user-managed） |

Cloud Run サービスアカウント（`913363513517-compute@developer.gserviceaccount.com`）に `roles/secretmanager.secretAccessor` を付与済み。

シークレットの更新手順:

```bash
# 新しいバージョンを追加
echo -n "<new-key>" | gcloud secrets versions add GOOGLE_API_KEY \
  --data-file=- --project=visa-codex-mvp

# Cloud Run に反映（latest参照のため再デプロイで自動反映）
gcloud run services update visa-app \
  --region asia-northeast1 \
  --project visa-codex-mvp \
  --update-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest"
```

## GCPリソース

| リソース | 値 |
|---|---|
| GCP Project | `visa-codex-mvp` |
| Account | `yohei7328@gmail.com` |
| Region | `asia-northeast1` |
| Cloud Run Service | `visa-app` (`https://visa-app-913363513517.asia-northeast1.run.app`) |
| Cloud Run Job | `codex-runner-job` |
| GCS Bucket | `visa-codex-mvp-data` |
| Firestore Collection | `cases`, `sessions` |
