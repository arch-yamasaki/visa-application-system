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

### Python

backend の Python コマンドは、system / Homebrew / pyenv の `python3` を直接使わず、project-local venv の Python を使う。

初回だけ:

```bash
cd backend
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pytest
```

以後:

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python -m uvicorn main:app --reload --port 8080
```

`python3 -m pytest` や bare `pytest` は使わない。`python3` は環境によって Homebrew Python を拾い、プロジェクト側に入っている `pytest` などの依存を見失うことがある。

## 本番環境でのAPIアクセス

本番（Cloud Run）ではフロントエンドとバックエンドが同一コンテナで動作する。フロントエンドは開発時と同様に `/api/*` プレフィックス付きでAPIを呼ぶ。`StripApiPrefixMiddleware`（backend/main.py）が `/api/` プレフィックスを除去し、FastAPIのルート（`/cases/...` 等）にリライトする。

Chrome拡張（rasens-autofill）はバックエンドAPIに直接 `/cases/...` でアクセスするため、ミドルウェアを経由しない。

## 抽出エンジン

| エンジン | 方式 | 用途 |
|---|---|---|
| Gemini | 同期。PDF/テキスト→Gemini API→構造化JSON | 通常の申請書類抽出 |
| Codex | 非同期。Cloud Run Job→codex exec→結果収穫 | 複雑な分析・統合処理 |

## autofill連携

- `backend/application_data.py` — canonical `case_data`、RASENSフォーム台帳、mapping v2、設定値から Chrome拡張投入用の `rows` を生成する。
- `GET /cases/{case_id}/application-data` — Chrome拡張（rasens-autofill）が呼び出すエンドポイント。Chrome拡張は返却された `rows` をRASENS DOMへ入力し、mappingや変換は解釈しない。

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
| `INTERMEDIARY_NAME` | 取次者 氏名 | `asia-northeast1`（user-managed） |
| `INTERMEDIARY_POSTAL_CODE` | 取次者 郵便番号 | `asia-northeast1`（user-managed） |
| `INTERMEDIARY_ADDRESS` | 取次者 住所 | `asia-northeast1`（user-managed） |
| `INTERMEDIARY_ORGANIZATION` | 取次者 所属機関 | `asia-northeast1`（user-managed） |
| `INTERMEDIARY_PHONE` | 取次者 電話番号 | `asia-northeast1`（user-managed） |

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

取次者情報は案件書類やGemini抽出ではなく、Cloud Run の固定設定から注入する。実値はrepoに書かず、Secret Manager または Cloud Run 環境変数で管理する。

```bash
# 例: Secret Manager に取次者情報を登録
echo -n "<intermediary-name>" | gcloud secrets versions add INTERMEDIARY_NAME \
  --data-file=- --project=visa-codex-mvp

# Cloud Run に反映
gcloud run services update visa-app \
  --region asia-northeast1 \
  --project visa-codex-mvp \
  --update-secrets="INTERMEDIARY_NAME=INTERMEDIARY_NAME:latest,INTERMEDIARY_POSTAL_CODE=INTERMEDIARY_POSTAL_CODE:latest,INTERMEDIARY_ADDRESS=INTERMEDIARY_ADDRESS:latest,INTERMEDIARY_ORGANIZATION=INTERMEDIARY_ORGANIZATION:latest,INTERMEDIARY_PHONE=INTERMEDIARY_PHONE:latest"
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
