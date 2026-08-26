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
cd backend && .venv/bin/python -m uvicorn main:app --reload --port 8080
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

実画面QAは Chrome DevTools MCP を使う。レビュー画面、PDF bbox、Network/Console の確認手順は `../docs/shared/chrome_devtools_mcp_qa.md` を参照。

## 本番環境でのAPIアクセス

本番（Cloud Run）ではフロントエンドとバックエンドが同一コンテナで動作する。フロントエンドは開発時と同様に `/api/*` プレフィックス付きでAPIを呼ぶ。`StripApiPrefixMiddleware`（backend/main.py）が `/api/` プレフィックスを除去し、FastAPIのルート（`/cases/...` 等）にリライトする。

Chrome拡張（rasens-autofill）はバックエンドAPIに直接 `/cases/...` でアクセスするため、ミドルウェアを経由しない。

## 認証・データ分離

Firebase Authentication（Identity Platform, プロジェクト visa-codex-mvp）でログインし、
API は全ルート認証必須（`backend/auth.py` の `require_user`）。

- 認証: Bearer トークン（Firebase ID token）を検証し、Firestore `users/{uid}` に登録済みのユーザーだけ通す。自由サインアップは不可（管理者発行制）
- 認可: `cases` / `sessions` は `org_id` 単位で分離。作成時に `org_id` / `owner_uid` を付与し、一覧は org でフィルタ、個別取得は org 不一致を 404 にする（`_get_case` / `_get_session`）
- フロント: `src/auth/firebase.ts`（設定+authHeaders）、`src/store/authStore.ts`、`/login` ページ。API 呼び出しは `client.ts` が自動で Authorization を付与
- 書類表示: PDF/画像は認証付き `/content` を blob 取得して objectURL で表示、DOCX/XLSX preview は fetch + srcDoc（iframe src 直読みは不可）
- Chrome拡張: popup でメール/パスワードログイン（Identity Toolkit REST）。トークンは `chrome.storage.local`

ユーザー発行:

```bash
cd backend
# メール/パスワードのユーザー発行
.venv/bin/python scripts/manage_users.py create --email staff@example.com --password '...' --org genbaai
# Googleログインするユーザーの登録（パスワード不要）
.venv/bin/python scripts/manage_users.py create --email someone@gmail.com --org genbaai
.venv/bin/python scripts/manage_users.py list
```

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

`GOOGLE_API_KEY`（Gemini API用）は認証情報なので、GCP Secret Manager で管理し、Cloud Run の環境変数としてマウントする。

| シークレット名 | 用途 | レプリケーション |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API 認証キー | `asia-northeast1`（user-managed） |

Cloud Run サービスアカウント（`913363513517-compute@developer.gserviceaccount.com`）には、利用するシークレット単位で `roles/secretmanager.secretAccessor` を付与する。

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

### 取次者・受領方法の組織設定

取次者5項目と通知送信用メールアドレスは企業（`org_id`）単位で Firestore `org_settings/{org_id}` に保存する。案件書類やGemini抽出から生成せず、案件データからも上書きしない。`GET /org-settings` は組織メンバーが参照でき、`PATCH /org-settings` はadminだけが変更できる。受領方法は `メール Email` 固定で、通知メール再入力欄にも同じ設定値を投入する。

`chuo-business` については、現在 Firestore に保存されている `org_settings/chuo-business` が正本であり、変更はadminがvisa-appの「組織設定」画面から行う。以前に大阪の公開情報を基に検討した値は旧前提なので、取次者設定へコピーしたり現行値の上書きに使ったりしない。下の保守用CLI例にある奈良県の住所は誤記ではないが、この文書の記載ではなく Firestore の現在値を優先する。

| Firestoreフィールド | 用途 |
|---|---|
| `intermediary.name` | 取次者 氏名 |
| `intermediary.postal_code` | 取次者 郵便番号 |
| `intermediary.address` | 取次者 住所 |
| `intermediary.organization` | 取次者 所属機関 |
| `intermediary.phone` | 取次者 電話番号 |
| `receiving_method.notification_email` | 通知送信用メールアドレス |

`/api` 経路では組織設定だけを参照し、未登録なら `fillable=false` にする。低レベルの `application_data` 生成関数には既存ローカル検証向けに `INTERMEDIARY_*` 5件のfallbackを残すが、組織設定が正本。取次者5項目と通知メールがすべて揃う場合だけ自動入力可能にする。

```bash
# 管理画面を使えない場合の保守用CLI（実行するとFirestoreへ書き込む）
.venv/bin/python scripts/manage_users.py org-settings set \
  --org chuo-business --name '<取次者氏名>' --postal-code '<半角数字>' \
  --address '奈良県奈良市宝来4丁目13番7号' --organization '<所属機関>' \
  --phone '<半角数字>' --notification-email 'promot1@gold.ocn.ne.jp'

.venv/bin/python scripts/manage_users.py org-settings list --org chuo-business
```

## GCPリソース

| リソース | 値 |
|---|---|
| GCP Project | `visa-codex-mvp` |
| Account | `yohei7328@gmail.com` |
| Region | `asia-northeast1` |
| Cloud Run Service | `visa-app` (`https://visa-app-913363513517.asia-northeast1.run.app`) |
| Cloud Run Job | `codex-runner-job` |
| Cloud Scheduler Job | `visa-app-warmup`（5分毎に `/` をGETしてコールドスタート回避） |
| GCS Bucket | `visa-codex-mvp-data` |
| Firestore Collection | `cases`, `sessions`, `users`, `org_settings` |
