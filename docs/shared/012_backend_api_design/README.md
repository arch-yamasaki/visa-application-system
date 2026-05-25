# visa-app バックエンドAPI・抽出エンジン設計

> 対象コード: `visa-app/backend/main.py` および `visa-app/backend/extractors/`
>
> 古いGemini extractor設計ドラフトは、現行実装とのズレが大きいため削除済み。実装判断はこの文書と対象コードを確認する。

---

## 1. 概要

FastAPIバックエンド（`codex-orchestrator`）は、在留資格申請のケース管理・書類管理・抽出エンジン呼び出しを担う中核サービス。Cloud Run上で稼働し、以下の3つのGCPサービスと連携する。

| GCPサービス | 用途 |
|---|---|
| **Firestore** | ケース（cases）・セッション（sessions）のメタデータ永続化 |
| **Cloud Storage (GCS)** | アップロード書類、Codexプロンプト/成果物の保存 |
| **Cloud Run Jobs** | Codex CLI非同期実行（codex-runner-job） |

環境変数で制御される主要設定:

```python
GCS_BUCKET       = "visa-codex-mvp-data"
GCP_PROJECT      = "visa-codex-mvp"
GCP_REGION       = "asia-northeast1"
CLOUD_RUN_JOB_NAME = "codex-runner-job"
```

抽出エンジンは2系統:

- **Gemini** -- 同期。Gemini 3 Flash にPDF/テキストを直接送信し、構造化JSONを即時取得。
- **Codex** -- 非同期。Cloud Run Job経由でCodex CLIを実行し、ポーリングで結果を収穫。

---

## 2. APIエンドポイント一覧

### 2.1 ケース管理

| メソッド | パス | 説明 | リクエスト | レスポンス |
|---|---|---|---|---|
| `POST` | `/cases` | 新規ケース作成 | `CreateCaseRequest` (application_type, target_status) | `{case_id, workflow_state, created_at}` |
| `GET` | `/cases` | ケース一覧取得 | Query: `limit` (1-100), `workflow_state` | ケースドキュメントの配列 |
| `GET` | `/cases/{case_id}` | ケース詳細取得 | -- | ケースドキュメント全体 |
| `PATCH` | `/cases/{case_id}` | ケース更新 | `UpdateCaseRequest` (case_data, field_metadata, workflow_state) | 更新後のケースドキュメント |

### 2.2 ドキュメント管理

| メソッド | パス | 説明 | リクエスト | レスポンス |
|---|---|---|---|---|
| `POST` | `/cases/{case_id}/documents` | 書類アップロード | `multipart/form-data` (file, document_role) | `{document_id, file_name, gcs_path, document_role}` |
| `GET` | `/cases/{case_id}/documents` | 書類一覧取得 | -- | `{documents: [...]}` |
| `GET` | `/cases/{case_id}/documents/{document_id}/url` | 署名付きURL取得 | -- | `{signed_url, document_id, file_name}` |
| `GET` | `/cases/{case_id}/documents/{document_id}/content` | 書類バイナリ直接配信 | -- | ファイルバイナリ (Response) |
| `GET` | `/cases/{case_id}/documents/{document_id}/sheets` | xlsxシート名一覧 | -- | `{sheets: ["Sheet1", ...]}` |
| `GET` | `/cases/{case_id}/documents/{document_id}/preview` | 書類プレビュー | Query: `sheet` (xlsx用) | docx/xlsx→HTML変換、PDF/画像→そのまま配信 |

### 2.3 抽出

| メソッド | パス | 説明 | リクエスト | レスポンス |
|---|---|---|---|---|
| `POST` | `/cases/{case_id}/extract` | 抽出実行 | `ExtractRequest` (backend, pattern) | Gemini: `{status, workflow_state}` / Codex: `{session_id, status}` |
| `GET` | `/cases/{case_id}/extraction-status` | 抽出ステータス確認 | -- | `{status, session_id}` |

### 2.4 セッション管理（Codex直接操作用）

| メソッド | パス | 説明 | リクエスト | レスポンス |
|---|---|---|---|---|
| `POST` | `/sessions` | セッション作成・Job起動 | `PromptRequest` (prompt) | `{session_id, run_id, status}` |
| `GET` | `/sessions` | セッション一覧（直近20件） | -- | セッションドキュメントの配列 |
| `GET` | `/sessions/{session_id}` | セッション詳細 | -- | セッション + latest_run |
| `GET` | `/sessions/{session_id}/result` | 実行結果取得 | -- | `{session_id, run_id, result}` |
| `GET` | `/sessions/{session_id}/files` | ワークスペースファイル一覧 | -- | `{files: [...]}` |
| `GET` | `/sessions/{session_id}/files/{file_path}` | ファイルダウンロード | -- | FileResponse |

### 2.5 フロントエンド

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/` | `static/index.html` を配信 |

---

## 3. ケース管理フロー

### ワークフロー状態遷移

```
draft → extracting → needs_review → ready_to_fill
                   ↘ extraction_failed
```

- `draft`: 作成直後。書類アップロード待ち。
- `extracting`: 抽出処理中（Gemini同期/Codex非同期）。
- `needs_review`: 抽出完了。人間によるレビュー待ち。
- `ready_to_fill`: レビュー完了、フォーム自動入力可能。`confirmed_at` が記録される。
- `extraction_failed`: 抽出失敗。

### CRUD操作

1. **Create**: `POST /cases` -- `case_id`（`case_`プレフィックス + 12桁hex）を自動生成。初期`case_data`にはスキーマバージョン、申請種別、在留資格種別を格納。
2. **Read**: `GET /cases/{case_id}` -- Firestoreドキュメント全体を返却。
3. **Update**: `PATCH /cases/{case_id}` -- `case_data`, `field_metadata`, `workflow_state` を部分更新。`workflow_state` が `ready_to_fill` に変更されると `confirmed_at` を自動記録。
4. **List**: `GET /cases` -- `created_at` 降順、`workflow_state` でフィルタ可能。

---

## 4. ドキュメント管理

### アップロードからメタデータ管理までの流れ

```
[クライアント]
  │ POST /cases/{case_id}/documents
  │ (multipart: file + document_role)
  ▼
[FastAPI]
  │ 1. ケース存在確認（Firestore）
  │ 2. document_id 生成（doc_ + 8桁hex）
  │ 3. GCSにアップロード
  │    パス: cases/{case_id}/documents/{document_id}_{original_filename}
  │ 4. Firestoreの document_manifest.documents に ArrayUnion で追記
  ▼
[レスポンス]
  {document_id, file_name, gcs_path, document_role}
```

### ドキュメントエントリ構造

```json
{
  "document_id": "doc_a1b2c3d4",
  "file_name": "passport.pdf",
  "gcs_path": "cases/case_xxxx/documents/doc_a1b2c3d4_passport.pdf",
  "document_role": "applicant_document_bundle",
  "uploaded_at": "2026-05-17T10:00:00+00:00"
}
```

### プレビュー対応

`GET /cases/{case_id}/documents/{document_id}/preview` は拡張子に応じて変換:

| 拡張子 | 処理 |
|---|---|
| `.docx` | python-docx でパース → HTML変換（段落+テーブル） |
| `.xlsx` | openpyxl でパース → HTML変換（結合セル対応、シート指定可） |
| `.pdf`, `.png`, `.jpg` | バイナリをそのまま配信 |

---

## 5. 抽出エンジン切替

`POST /cases/{case_id}/extract` のリクエストボディ:

```python
class ExtractRequest(BaseModel):
    backend: str = "gemini"   # "gemini" | "codex"
    pattern: str = "auto"     # "auto" | "text_only" | "pdf_direct" | "text_and_image"
```

### 5.1 Geminiパス（同期）

`backend == "gemini"` の場合、`_start_gemini_extraction()` → `_extract_with_gemini()` が呼ばれる。

#### ファイル分類

書類は拡張子で3カテゴリに分類される:

| カテゴリ | 拡張子 | 処理 |
|---|---|---|
| **PDF** | `.pdf` | `pdf_contents` + `image_entries` に追加 |
| **テキスト書類** | `.xlsx`, `.xls` | `extract_xlsx()` でテキスト化 → `text_contents` |
| | `.docx`, `.doc` | `extract_docx()` でテキスト化 → `text_contents` |
| **画像** | `.png`, `.jpg`, `.jpeg` | `image_entries` に追加 |

#### パターン選択ロジック（`pattern == "auto"` の場合）

```python
has_pdfs = any(fname.lower().endswith(".pdf") for _, fname, _ in file_entries)
has_images_only = image_entries and not has_pdfs
pattern = "text_and_image" if has_images_only else "pdf_direct"
```

- PDFが1つでもあれば → `pdf_direct`
- PDFなし＋画像あり → `text_and_image`

#### 3つの抽出パターン

| パターン | 関数 | 入力 | 特徴 |
|---|---|---|---|
| `text_only` | `extract_text_only()` | Cloud Vision OCRテキスト + xlsx/docxテキスト | Vision API依存。テキストのみでGeminiに送信 |
| `pdf_direct` | `extract_pdf_direct()` | PDFバイナリ直接 + xlsx/docxテキスト | **推奨**。GeminiがPDFを直接読むため精度高い。Vision API不要 |
| `text_and_image` | `extract_with_images()` | OCRテキスト + 画像バイナリ + xlsx/docxテキスト | 画像ファイル（png/jpg）がある場合用 |

#### bbox付与（pdf_direct / text_and_image）

`pdf_direct` と `text_and_image` パターンでは、抽出後に `locate_bboxes()` が呼ばれ、対象フィールドの `source_refs` に bounding box 座標が付与される。

対象フィールド（`BBOX_TARGET_FIELDS`）:

```
applicant.name_roman, applicant.nationality_region, applicant.birth_date,
applicant.passport.number, employment.job_title,
employment.monthly_salary, employment.work_location,
applicant.education.0.school_name, applicant.education.0.major_field,
employer.name, employer.capital_jpy, ...
```

処理手順:
1. 対象フィールドの `source_refs` から `(document_id, page)` をグループ化
2. PyMuPDF でPDFページを300dpi PNG画像に変換
3. Gemini に画像 + text_quote を送信し、`[y_min, x_min, y_max, x_max]`（0-1000正規化座標）を取得
4. `source_refs` に `bbox` オブジェクトとして反映

#### Gemini API呼び出し

```python
# モデル: gemini-3-flash-preview（環境変数で変更可）
response = client.models.generate_content(
    model=MODEL_NAME,
    contents=[*contents, prompt],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.0,
        max_output_tokens=65536,
    ),
)
```

レスポンスJSONは `json_repair` でフォールバック修復される。また `field_metadata` の正規化処理として:
- `doc_id` → `document_id` への統一
- `page` のデフォルト値(1)・型変換
- `case_data` の全フィールドパスに対する `field_metadata` エントリの補完

### 5.2 Codexパス（非同期）

`backend == "codex"` の場合、`_start_codex_extraction()` が呼ばれる。

#### 非同期実行フロー

```
POST /cases/{case_id}/extract {backend: "codex"}
  │
  ├─ 1. プロンプト生成（書類一覧 + GCSパスを含む）
  ├─ 2. session_id / run_id 生成
  ├─ 3. プロンプトをGCSにアップロード
  │     → sessions/{session_id}/runs/{run_id}/prompt.txt
  ├─ 4. Firestoreにsession/runドキュメント作成（status: queued）
  ├─ 5. ケースを extracting に更新、extraction_session_id を記録
  └─ 6. Cloud Run Job起動（fire-and-forget）
       環境変数: SESSION_ID, RUN_ID, PROMPT_GCS_URI, GCS_BUCKET, FIRESTORE_DOC_PATH

[Cloud Run Job: codex-runner-job]
  │ Codex CLI実行 → 結果をGCSに保存
  │   → sessions/{session_id}/runs/{run_id}/workspace.tar.zst
  │   → sessions/{session_id}/runs/{run_id}/last_message.txt
  └─ Firestoreのstatus更新（completed/failed）

GET /cases/{case_id}/extraction-status
  │ status == "completed" かつ case.workflow_state == "extracting" の場合:
  └─ _harvest_extraction_results() を実行
       workspace.tar.zst を展開 → generated/ 配下の JSON を case に反映
       → case_data.json, review.json, field_metadata.json
```

---

## 6. Firestoreデータモデル

### 6.1 `cases/{case_id}` コレクション

```
cases/
  └─ {case_id}/                          # 例: case_a1b2c3d4e5f6
       ├─ case_id: string
       ├─ workflow_state: string          # draft | extracting | needs_review | ready_to_fill | extraction_failed
       ├─ created_at: string (ISO 8601)
       ├─ updated_at: string (ISO 8601)
       ├─ confirmed_at: string | null     # ready_to_fill 移行時に記録
       ├─ extraction_session_id: string | null  # Codex抽出時のsession_id
       ├─ case_data: {                    # 抽出された構造化データ
       │    schema_version: "2.0",
       │    case: {case_id, application_type, target_status, workflow_state},
       │    applicant: {name_roman, nationality_region, birth_date, passport: {...}, education: [...], ...},
       │    entry_plan: {...},
       │    employment: {job_title, monthly_salary, work_location, activity_details, ...},
       │    employer: {name, capital_jpy, representative_name, ...}
       │  }
       ├─ field_metadata: {               # フィールドごとの抽出根拠
       │    "applicant.name_roman": {
       │      source_refs: [{document_id, page, text_quote, confidence, bbox?}]
       │    },
       │    ...
       │  }
       ├─ review: {                       # レビュー所見
       │    missing_items: [...],
       │    weak_evidence: [...],
       │    contradictions: [...],
       │    needs_human_judgment: [...]
       │  }
       └─ document_manifest: {
            documents: [
              {document_id, file_name, gcs_path, document_role, uploaded_at},
              ...
            ]
          }
```

### 6.2 `sessions/{session_id}` コレクション

```
sessions/
  └─ {session_id}/                       # 例: sess_a1b2c3d4e5f6
       ├─ session_id: string
       ├─ status: string                 # queued | running | completed | launch_failed
       ├─ created_at: string
       ├─ updated_at: string
       ├─ latest_run_id: string
       ├─ prompt_preview: string         # 先頭200文字
       ├─ linked_case_id: string | null  # ケース経由の場合のみ
       │
       └─ runs/                          # サブコレクション
            └─ {run_id}/
                 ├─ run_id: string
                 ├─ status: string       # queued | running | completed | launch_failed
                 ├─ created_at: string
                 ├─ prompt_gcs_uri: string
                 └─ error: string | null
```

---

## 7. GCSバケット構造

バケット名: `visa-codex-mvp-data`

```
visa-codex-mvp-data/
  ├─ cases/
  │    └─ {case_id}/
  │         └─ documents/
  │              ├─ {document_id}_{original_filename}    # アップロード書類
  │              ├─ doc_a1b2c3d4_passport.pdf
  │              └─ doc_e5f6g7h8_employment_contract.docx
  │
  └─ sessions/
       └─ {session_id}/
            └─ runs/
                 └─ {run_id}/
                      ├─ prompt.txt              # Codex実行プロンプト
                      ├─ last_message.txt         # Codex最終出力
                      └─ workspace.tar.zst        # Codexワークスペース全体
```

---

## 8. 具体例: 新規ケースで書類3点をGemini抽出する流れ

### Step 1: ケース作成

```
POST /cases
Content-Type: application/json

{
  "application_type": "certificate_of_eligibility",
  "target_status": "engineer_humanities_international"
}
```

レスポンス:

```json
{
  "case_id": "case_1a2b3c4d5e6f",
  "workflow_state": "draft",
  "created_at": "2026-05-17T10:00:00+00:00"
}
```

### Step 2: 書類アップロード（3回）

```
POST /cases/case_1a2b3c4d5e6f/documents
Content-Type: multipart/form-data

file: passport.pdf
document_role: applicant_document_bundle
```

```json
{"document_id": "doc_aaa11111", "file_name": "passport.pdf", "gcs_path": "cases/case_1a2b3c4d5e6f/documents/doc_aaa11111_passport.pdf", "document_role": "applicant_document_bundle"}
```

同様に `employment_contract.docx`、`company_info.xlsx` をアップロード。

### Step 3: Gemini抽出実行

```
POST /cases/case_1a2b3c4d5e6f/extract
Content-Type: application/json

{
  "backend": "gemini",
  "pattern": "auto"
}
```

内部処理:
1. `workflow_state` を `extracting` に更新
2. 3ファイルをGCSからダウンロード
3. ファイル分類:
   - `passport.pdf` → `pdf_contents` + `image_entries`
   - `employment_contract.docx` → `extract_docx()` → `text_contents`
   - `company_info.xlsx` → `extract_xlsx()` → `text_contents`
4. `pattern == "auto"` → PDFあり → `pdf_direct` を選択
5. `extract_pdf_direct()`: PDFバイナリ + docx/xlsxテキストをGeminiに送信
6. Geminiが `{case_data, review, field_metadata}` を返却
7. `locate_bboxes()`: 対象フィールドのbbox座標を付与
8. Firestoreに結果を保存、`workflow_state` を `needs_review` に更新

レスポンス:

```json
{
  "status": "completed",
  "workflow_state": "needs_review"
}
```

### Step 4: 結果確認

```
GET /cases/case_1a2b3c4d5e6f
```

レスポンス（抜粋）:

```json
{
  "case_id": "case_1a2b3c4d5e6f",
  "workflow_state": "needs_review",
  "case_data": {
    "schema_version": "2.0",
    "case": {"case_id": "case_1a2b3c4d5e6f", "application_type": "certificate_of_eligibility", "target_status": "engineer_humanities_international"},
    "applicant": {"name_roman": "YAMADA TARO", "nationality_region": "Vietnam", "birth_date": "1995-03-15", "passport": {"number": "B12345678"}},
    "entry_plan": {"main_activity_category": "技術・人文知識・国際業務", "purpose_of_entry": "技術・人文知識・国際業務"},
    "employer": {"name": "Example株式会社", "capital_jpy": "10,000,000"},
    "employment": {"job_title": "ソフトウェアエンジニア", "monthly_salary": "250,000"}
  },
  "field_metadata": {
    "applicant.name_roman": {
      "source_refs": [{
        "document_id": "doc_aaa11111",
        "page": 1,
        "text_quote": "YAMADA TARO",
        "confidence": 0.95,
        "bbox": {"y_min": 120, "x_min": 200, "y_max": 145, "x_max": 450}
      }]
    }
  },
  "review": {
    "missing_items": [],
    "weak_evidence": [],
    "contradictions": [],
    "needs_human_judgment": ["activity_detailsの具体性を確認してください"]
  }
}
```

---

## 9. Codex非同期抽出の具体例

### Step 1: 抽出開始

```
POST /cases/case_1a2b3c4d5e6f/extract
Content-Type: application/json

{
  "backend": "codex",
  "pattern": "auto"
}
```

内部処理:
1. 書類一覧からプロンプトを自動生成（GCSパス付き）
2. `session_id`（`sess_` + 12桁hex）、`run_id`（`run_` + タイムスタンプ + 4桁hex）を生成
3. プロンプトをGCSにアップロード → `sessions/{session_id}/runs/{run_id}/prompt.txt`
4. Firestore に session / run ドキュメントを作成
5. ケースの `extraction_session_id` を記録、`workflow_state` を `extracting` に更新
6. Cloud Run Job を環境変数オーバーライドで起動（fire-and-forget）

レスポンス:

```json
{
  "session_id": "sess_abc123def456",
  "status": "running"
}
```

### Step 2: ステータスポーリング

```
GET /cases/case_1a2b3c4d5e6f/extraction-status
```

実行中:

```json
{"status": "running", "session_id": "sess_abc123def456"}
```

### Step 3: 完了後の自動harvest

`GET /cases/{case_id}/extraction-status` を呼んだ際に `status == "completed"` かつ `workflow_state == "extracting"` であれば、`_harvest_extraction_results()` が自動実行される。

harvest処理:
1. `sessions/{session_id}/runs/{run_id}/workspace.tar.zst` をGCSからダウンロード
2. `tar --zstd -xf` で展開
3. `generated/` ディレクトリ配下の以下を探索:
   - `generated/case_data.json` → `case_data` フィールドに反映
   - `generated/review.json` → `review` フィールドに反映
   - `generated/field_metadata.json` → `field_metadata` フィールドに反映
4. ケースの `workflow_state` を `needs_review` に更新

完了後のレスポンス:

```json
{"status": "completed", "session_id": "sess_abc123def456"}
```

以降は `GET /cases/{case_id}` で抽出結果を確認し、レビュー → `PATCH` で `ready_to_fill` に遷移させる。
