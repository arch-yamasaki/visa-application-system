# Gemini 抽出バックエンド設計

> 作成日: 2026-05-14
> ステータス: Draft

---

## 1. 概要

現在の `POST /cases/{id}/extract` は Codex (OpenAI) ベースで、Cloud Run Job を起動し workspace tarball から結果を収穫する方式。これを Gemini 3 Flash による同期的な構造化抽出に置き換える。

**変更の核心**: Codex 方式は「Job 起動 → ポーリング → tarball 展開 → JSON 収穫」という非同期パイプラインだったが、Gemini 方式は「API 呼び出し → JSON レスポンス」の同期処理になる。抽出レイテンシが分単位から秒単位に短縮される。

---

## 2. ディレクトリ構成

```
codex-cloud/orchestrator/
  extractors/
    __init__.py
    types.py            # 共通型: OcrResult, PageResult, WordResult, ExtractionResult
    gemini.py           # Gemini 3 Flash 構造化抽出（3パターン）
    vision.py           # Google Cloud Vision API OCR
    pdf_text.py         # PyMuPDF テキストレイヤー抽出
    prompt_template.py  # プロンプトテンプレート生成
  main.py               # 既存 + extract エンドポイント拡張
  tests/
    test_gemini.py
    test_vision.py
    test_pdf_text.py
```

---

## 3. 共通型（types.py）

```python
from dataclasses import dataclass

@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

@dataclass
class WordResult:
    text: str
    bbox: BoundingBox | None
    confidence: float

@dataclass
class PageResult:
    page_number: int       # 1-indexed
    text: str              # ページ全体のプレーンテキスト
    words: list[WordResult]

@dataclass
class OcrResult:
    pages: list[PageResult]
    document_id: str       # document_manifest の document_id に対応

@dataclass
class ExtractionResult:
    case_data: dict        # case_data.schema.json 準拠
    review: dict           # review.schema.json 準拠
    field_metadata: dict   # フィールド別の抽出根拠
```

### 設計判断

- dataclass を使用（Pydantic は main.py のリクエスト/レスポンスモデルのみ、内部データ構造は軽量に）
- `BoundingBox` は Vision API の座標をそのまま保持。field_metadata への座標マッピングに使用
- `OcrResult.document_id` で書類単位の追跡を可能にする

---

## 4. 処理パターン

### 4.1 パターン A: text_only

```
GCS PDF → Vision API OCR → OCRテキスト → Gemini → ExtractionResult
         └→ PyMuPDF fallback（テキストレイヤーあり）
```

- **用途**: 雇用条件通知書、会社資料など活字テキスト中心の書類
- **利点**: トークン最小、コスト最安
- **欠点**: レイアウト・画像情報が失われる

### 4.2 パターン B: pdf_direct

```
GCS PDF → PDF bytes → Gemini（マルチモーダル入力） → ExtractionResult
```

- **用途**: パスポート、在留カード、卒業証明書など視覚情報が重要な書類
- **利点**: 実装最シンプル、手書き・スタンプ対応
- **欠点**: 座標情報が取れない（field_metadata の source_refs に text_quote のみ）

### 4.3 パターン C: text_and_image

```
GCS PDF → Vision API OCR → OCRテキスト ─┐
    │                                     ├→ Gemini → ExtractionResult
    └→ PDF bytes ─────────────────────────┘
```

- **用途**: 履歴書、成績証明書など表形式＋手書き混在の書類
- **利点**: 最高精度（テキスト＋視覚の相互補完）
- **欠点**: コスト最大、実装が複雑

### 4.4 auto モードの選択ロジック

`pattern: "auto"` の場合、以下のルールで自動選択:

```python
def _select_pattern(documents: list[dict]) -> str:
    """書類の document_role に基づいてパターンを選択。"""
    roles = {d["document_role"] for d in documents}

    # 画像系書類が含まれる場合は pdf_direct
    image_roles = {"passport", "residence_card", "photo", "diploma"}
    if roles & image_roles:
        return "pdf_direct"

    # 複合系書類が含まれる場合は text_and_image
    mixed_roles = {"resume", "transcript", "applicant_document_bundle"}
    if roles & mixed_roles:
        return "text_and_image"

    # テキスト系のみなら text_only
    return "text_only"
```

**MVP では `pdf_direct` をデフォルトとする**。理由:
1. 実装が最もシンプル
2. 調査レポートの推奨（Phase 1 = PDF直接入力）
3. 月100件で $1.65（コスト差は無視できる）
4. `applicant_document_bundle`（パスポート～履歴書の混合PDF）が主な入力形態

auto モードの書類分類ロジックは Phase 2 で精度検証後に有効化する。

---

## 5. API 設計

### 5.1 エンドポイント拡張

`POST /cases/{case_id}/extract`

**リクエストボディ（新規追加）**:

```json
{
  "backend": "gemini",
  "pattern": "auto"
}
```

| パラメータ | 型 | デフォルト | 値 |
|---|---|---|---|
| `backend` | string | `"gemini"` | `"gemini"` \| `"codex"` |
| `pattern` | string | `"auto"` | `"auto"` \| `"text_only"` \| `"pdf_direct"` \| `"text_and_image"` |

**レスポンス（gemini backend）**:

```json
{
  "case_id": "case_xxxxxxxxxxxx",
  "backend": "gemini",
  "pattern": "pdf_direct",
  "status": "completed",
  "extraction_result": {
    "case_data": { "..." },
    "review": { "..." },
    "field_metadata": { "..." }
  }
}
```

Gemini 方式は同期レスポンス。Codex 方式は従来通り非同期（`status: "running"` + ポーリング）。

### 5.2 Pydantic モデル

```python
class ExtractRequest(BaseModel):
    backend: str = "gemini"     # "gemini" | "codex"
    pattern: str = "auto"       # "auto" | "text_only" | "pdf_direct" | "text_and_image"

class ExtractResponse(BaseModel):
    case_id: str
    backend: str
    pattern: str
    status: str
    extraction_result: dict | None = None
    session_id: str | None = None       # codex backend のみ
    error: str | None = None
```

### 5.3 main.py の変更

```python
@app.post("/cases/{case_id}/extract")
def start_extraction(case_id: str, body: ExtractRequest = ExtractRequest()):
    # ... 既存の case/document バリデーション ...

    if body.backend == "codex":
        return _extract_codex(case_id, ref, data, documents)  # 既存ロジックを関数化

    return _extract_gemini(case_id, ref, data, documents, body.pattern)
```

既存の Codex 抽出ロジック（L500-588）は `_extract_codex()` に切り出す。後方互換のため `backend` のデフォルトは `"gemini"` とし、明示的に `"codex"` を指定した場合のみ旧方式を使用。

---

## 6. 各モジュール設計

### 6.1 vision.py — Cloud Vision API OCR

```python
async def ocr_document(gcs_path: str, document_id: str) -> OcrResult:
    """GCS上のPDF/画像をCloud Vision APIでOCRし、テキスト＋座標を返す。"""
```

- `google-cloud-vision` の `AsyncBatchAnnotateFilesRequest` を使用
- PDF は最大 2,000 ページまで対応（在留資格では 30 ページ未満）
- `TEXT_DETECTION` で全文テキスト + 単語単位の BoundingBox を取得
- 結果を `OcrResult` に変換

### 6.2 pdf_text.py — PyMuPDF テキスト抽出

```python
def extract_text_from_pdf(pdf_bytes: bytes, document_id: str) -> OcrResult:
    """PDFのテキストレイヤーからテキストを抽出。OCR不要な場合のフォールバック。"""
```

- `pymupdf` (旧 `fitz`) でテキストレイヤーを抽出
- テキストレイヤーが空（スキャンPDF）の場合は空の OcrResult を返す
- Vision API より高速・無料だが、スキャンPDFには効かない

### 6.3 gemini.py — Gemini 構造化抽出

```python
async def extract_with_gemini(
    documents: list[dict],      # document_manifest のエントリ
    ocr_results: list[OcrResult] | None,  # パターンA/Cの場合
    pdf_contents: list[tuple[str, bytes]] | None,  # パターンB/Cの場合
    case_context: dict,         # case_id, application_type, target_status
    prompt: str,                # prompt_template.py で生成
) -> ExtractionResult:
    """Gemini APIを呼び出し、構造化データを抽出する。"""
```

**Gemini API 呼び出しの構成**:

```python
import google.genai as genai

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3.0-flash",
    contents=contents,          # テキスト/PDF/画像の混合
    config=genai.types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=extraction_schema,  # case_data + review + field_metadata
        temperature=0.0,
    ),
)
```

**response_schema の構造**:

```python
extraction_schema = {
    "type": "object",
    "required": ["case_data", "review", "field_metadata"],
    "properties": {
        "case_data": {
            # case_data.schema.json から生成（$ref を展開）
        },
        "review": {
            # review.schema.json から生成
        },
        "field_metadata": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "source_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "document_id": {"type": "string"},
                                "page": {"type": "string"},
                                "text_quote": {"type": "string"},
                                "confidence": {"type": "string"}
                            }
                        }
                    }
                }
            }
        }
    }
}
```

**パターン別の contents 組み立て**:

```python
def _build_contents(
    pattern: str,
    prompt: str,
    ocr_results: list[OcrResult] | None,
    pdf_contents: list[tuple[str, bytes]] | None,
) -> list:
    parts = [genai.types.Part.from_text(prompt)]

    if pattern in ("text_only", "text_and_image") and ocr_results:
        for ocr in ocr_results:
            ocr_text = f"--- OCR: {ocr.document_id} ---\n"
            for page in ocr.pages:
                ocr_text += f"[Page {page.page_number}]\n{page.text}\n"
            parts.append(genai.types.Part.from_text(ocr_text))

    if pattern in ("pdf_direct", "text_and_image") and pdf_contents:
        for filename, pdf_bytes in pdf_contents:
            parts.append(genai.types.Part.from_bytes(
                data=pdf_bytes,
                mime_type="application/pdf",
            ))

    return [genai.types.Content(parts=parts)]
```

### 6.4 prompt_template.py — プロンプト生成

```python
def build_extraction_prompt(
    case_context: dict,
    document_descriptions: list[dict],
) -> str:
    """blind_single_case_prompt.md をベースにGemini向けプロンプトを生成。"""
```

既存の `blind_single_case_prompt.md` から以下を簡潔化:

- **削除**: `expected/` 参照禁止ルール（eval 専用、本番不要）
- **削除**: ファイルシステム操作の指示（Gemini は API なのでファイル操作しない）
- **削除**: `generated/` への書き出し指示（JSON レスポンスで返す）
- **保持**: 抽出優先順位、field_metadata 要件、レビュー方針、出力言語ルール
- **追加**: `response_schema` に合わせた出力構造の明示

プロンプトの核心部分:

```
あなたは日本の在留資格申請の構造化データを抽出するAIです。

## 抽出対象
- 案件ID: {case_id}
- 申請種別: {application_type}
- 対象在留資格: {target_status}

## 書類一覧
{document_descriptions}

## 抽出の優先順位
{既存プロンプトの「抽出の優先順位」セクション}

## 出力言語ルール
- case_data: 原本の言語をそのまま使用
- review: 説明テキストは日本語
- field_metadata: text_quote は原文から引用

## レビュー方針
{既存プロンプトの「レビュー方針」セクション}

## field_metadata 要件
{既存プロンプトの「field_metadata.json 出力要件」セクション}
```

---

## 7. 処理フロー全体

### 7.1 Gemini 抽出の処理フロー

```
POST /cases/{id}/extract  { backend: "gemini", pattern: "auto" }
  │
  ├── 1. Case & document_manifest の取得（Firestore）
  │
  ├── 2. パターン選択（auto → pdf_direct）
  │
  ├── 3. 書類取得（GCS → PDF bytes）
  │     ├── パターン A: Vision API OCR or PyMuPDF
  │     ├── パターン B: PDF bytes をそのまま保持
  │     └── パターン C: 両方
  │
  ├── 4. プロンプト生成（prompt_template.py）
  │
  ├── 5. Gemini API 呼び出し（gemini.py）
  │     └── response_schema で case_data + review + field_metadata を一括取得
  │
  ├── 6. field_metadata の座標補完（パターン A/C の場合）
  │     └── OCR の WordResult.bbox と text_quote をマッチングして座標を付与
  │
  ├── 7. Firestore 書き込み
  │     ├── cases/{id}.case_data = extraction_result.case_data
  │     ├── cases/{id}.review = extraction_result.review
  │     ├── cases/{id}.field_metadata = extraction_result.field_metadata
  │     └── cases/{id}.workflow_state = "needs_review"
  │
  └── 8. レスポンス返却
```

### 7.2 座標補完ロジック（field_metadata）

Gemini は画像内の座標を返せないため、OCR 結果から補完する:

```python
def _enrich_field_metadata_with_coords(
    field_metadata: dict,
    ocr_results: list[OcrResult],
) -> dict:
    """field_metadata の各エントリに、OCR結果からbbox座標を追加。"""
    for field_path, meta in field_metadata.items():
        for ref in meta.get("source_refs", []):
            text_quote = ref.get("text_quote", "")
            if not text_quote:
                continue
            # OCR結果から text_quote に最もマッチする単語列を検索
            matched_bbox = _find_bbox_for_quote(
                text_quote, ocr_results, ref.get("document_id")
            )
            if matched_bbox:
                ref["bbox"] = matched_bbox.__dict__
    return field_metadata
```

パターン B（pdf_direct）では OCR を実行しないため、座標は付与されない。Phase 2 で必要になった場合にのみ対応する。

---

## 8. Firestore 書き込み

既存の `cases/{id}` ドキュメント構造をそのまま利用:

```python
ref.update({
    "case_data": result.case_data,
    "review": result.review,
    "field_metadata": result.field_metadata,
    "workflow_state": "needs_review",
    "updated_at": _now_iso(),
    "extraction_backend": "gemini",
    "extraction_pattern": pattern,
})
```

新規フィールド:
- `extraction_backend`: `"gemini"` or `"codex"`（どちらで抽出したかの記録）
- `extraction_pattern`: 使用したパターン

既存フィールドの `extraction_session_id` は Codex 方式でのみ使用。Gemini 方式では `None` のまま。

---

## 9. エラーハンドリング

最小限の防御:

| エラー | 対応 |
|---|---|
| Gemini API レート制限 (429) | HTTPException(503) を返す。リトライはクライアント側 |
| Gemini API レスポンスが schema に合わない | HTTPException(502) + エラー詳細。`workflow_state` は変更しない |
| GCS からの PDF ダウンロード失敗 | HTTPException(502) |
| Vision API エラー（パターン A/C） | text_only → pdf_direct にフォールバック |

---

## 10. 依存パッケージ（requirements.txt 追加分）

```
google-genai>=1.0.0          # Gemini API (新 SDK)
google-cloud-vision>=3.0.0   # Cloud Vision OCR
pymupdf>=1.24.0              # PDF テキストレイヤー抽出
```

---

## 11. テスト設計

### test_gemini.py

```python
# 1. response_schema でのJSON構造化出力が case_data.schema.json に適合すること
# 2. パターン A/B/C 各々で contents が正しく組み立てられること
# 3. auto パターン選択ロジックのユニットテスト

def test_build_contents_text_only():
    """パターンA: OCRテキストのみがcontentsに含まれること"""

def test_build_contents_pdf_direct():
    """パターンB: PDF bytesのみがcontentsに含まれること"""

def test_build_contents_text_and_image():
    """パターンC: OCRテキスト+PDF bytes両方がcontentsに含まれること"""

def test_select_pattern_auto():
    """auto選択: document_roleに基づく正しいパターン選択"""
```

### test_vision.py

```python
# Vision API のレスポンスを OcrResult に正しく変換できること
def test_parse_vision_response():
    """Vision APIレスポンスからOcrResult変換"""

def test_bbox_extraction():
    """BoundingBox座標の正しい抽出"""
```

### test_pdf_text.py

```python
# PyMuPDF でテキストレイヤー抽出が正しく動作すること
def test_extract_text_layer():
    """テキストレイヤーありPDFからのテキスト抽出"""

def test_scanned_pdf_returns_empty():
    """スキャンPDF（テキストレイヤーなし）で空のOcrResultを返すこと"""
```

---

## 12. 実装順序

| ステップ | 内容 | ファイル |
|---|---|---|
| 1 | 共通型の定義 | `extractors/types.py` |
| 2 | プロンプトテンプレート | `extractors/prompt_template.py` |
| 3 | Gemini 抽出（パターン B のみ） | `extractors/gemini.py` |
| 4 | main.py エンドポイント拡張 | `main.py` |
| 5 | テスト | `tests/test_gemini.py` |
| 6 | Vision API OCR | `extractors/vision.py` |
| 7 | PyMuPDF テキスト抽出 | `extractors/pdf_text.py` |
| 8 | パターン A/C の実装 | `extractors/gemini.py` |
| 9 | 座標補完 | `extractors/gemini.py` |
| 10 | 残りテスト | `tests/test_vision.py`, `tests/test_pdf_text.py` |

**MVP（ステップ 1-5）**: パターン B（pdf_direct）のみで動作する最小実装。
**Phase 2（ステップ 6-10）**: 精度検証後に Vision API 連携を追加。
