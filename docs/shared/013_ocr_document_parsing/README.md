# ドキュメント解析・OCRパイプライン

visa-app の `backend/extractors/` パッケージの実装詳細。
申請書類（PDF/XLSX/DOCX/画像）からテキスト・構造化データを取り出し、Gemini で在留資格申請に必要な項目を JSON として抽出するパイプライン。

> 008 は Gemini の設計方針ドキュメント。本ドキュメントは extractors/ の実装詳細・処理フロー・具体例に特化する。

---

## 1. 概要

パイプラインは大きく3段階で構成される。

1. **テキスト抽出** -- ファイル形式に応じて PDF（PyMuPDF / Vision API OCR）、XLSX（openpyxl）、DOCX（python-docx）からテキストを取り出す
2. **Gemini 構造化抽出** -- 抽出テキスト（+必要に応じてPDF/画像バイナリ）を Gemini に渡し、`case_data` / `review` / `field_metadata` の3オブジェクトを含む JSON を取得
3. **Bbox 推定** -- 対象フィールドについて、PDFページを画像化し Gemini で座標（bounding box）を取得。フロントエンドのハイライト表示に使用

```
ファイル受信
  |
  +--[PDF]---> has_text_layer? --Yes--> PyMuPDF テキスト抽出 (pdf_text.py)
  |                             --No--> Vision API OCR (vision.py)
  +--[XLSX]--> openpyxl テキスト抽出 (xlsx.py)
  +--[DOCX]--> python-docx テキスト抽出 (docx_text.py)
  +--[画像]--> Vision API OCR (vision.py)
  |
  v
OcrResult (共通型)
  |
  v
Gemini 構造化抽出 (gemini.py)  <--- プロンプト (prompt_template.py)
  |
  v
ExtractionResult { case_data, review, field_metadata }
  |
  v
Bbox 推定 (bbox_locator.py) --- 対象フィールドの source_ref に bbox を付与
  |
  v
最終結果（bbox 付き field_metadata）
```

---

## 2. 対応ファイル形式と処理方法

| ファイル形式 | 使用ライブラリ | 処理内容 | 実装ファイル |
|---|---|---|---|
| PDF（テキストレイヤーあり） | PyMuPDF (`pymupdf`) | ページごとにテキスト＋単語座標を抽出 | `pdf_text.py` |
| PDF（テキストレイヤーなし） | PyMuPDF + Google Cloud Vision API | ページを300dpiで画像化→Vision API `DOCUMENT_TEXT_DETECTION` | `vision.py` |
| XLSX | `openpyxl` | シートごとにセル値をタブ区切りテキスト化 | `xlsx.py` |
| DOCX | `python-docx` | 段落テキスト＋テーブルセルを結合 | `docx_text.py` |
| 画像（PNG/JPEG等） | Google Cloud Vision API | `DOCUMENT_TEXT_DETECTION` で単語＋座標取得 | `vision.py` |

---

## 3. 共通型定義（types.py）

すべての抽出結果は以下のデータクラスに統一される。

### BoundingBox

```python
@dataclass
class BoundingBox:
    x: float      # 左上X座標
    y: float      # 左上Y座標
    width: float   # 幅
    height: float  # 高さ
```

PyMuPDF や Vision API が返す座標系をこの形式に正規化する。

### WordResult

```python
@dataclass
class WordResult:
    text: str                  # 単語テキスト
    bbox: BoundingBox | None   # 座標（XLSX/DOCXではNone）
    confidence: float          # 信頼度（PyMuPDFは常に1.0）
```

### PageResult

```python
@dataclass
class PageResult:
    page_number: int                              # ページ番号（1始まり）
    text: str                                     # ページ全体のテキスト
    words: list[WordResult] = field(default_factory=list)  # 単語リスト
```

XLSXではシート=ページ、DOCXでは文書全体=1ページとして扱う。

### OcrResult

```python
@dataclass
class OcrResult:
    document_id: str                              # 書類ID
    pages: list[PageResult] = field(default_factory=list)
```

### ExtractionResult

```python
@dataclass
class ExtractionResult:
    case_data: dict       # 申請人情報、学歴、職歴、雇用条件等の構造化データ
    review: dict          # 欠損・矛盾・要確認事項
    field_metadata: dict  # 各フィールドの抽出根拠（source_refs）
```

Gemini の出力を格納する最終型。`field_metadata` の各エントリは `source_refs` を持ち、どの `document_id` のどのページから抽出したかを記録する。

---

## 4. PDF処理の分岐（pdf_text.py / vision.py）

PDFファイルの処理はテキストレイヤーの有無で分岐する。統合関数 `vision.ocr_document()` がエントリーポイント。

### テキストレイヤー判定

```python
_MIN_TEXT_LENGTH = 20

def has_text_layer(pdf_bytes: bytes) -> bool:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total = sum(len(page.get_text().strip()) for page in doc)
    doc.close()
    return total >= _MIN_TEXT_LENGTH
```

全ページのテキスト合計が20文字以上ならテキストレイヤーありと判定。スキャン画像PDFは0文字になるためVision API OCRへ回る。

### 分岐ロジック（ocr_document）

```python
def ocr_document(file_bytes, file_name, document_id) -> OcrResult:
    if file_name.endswith(".pdf"):
        if has_text_layer(file_bytes):
            return extract_text(file_bytes, document_id)   # PyMuPDF直接
        return ocr_pdf(file_bytes, document_id)             # Vision API OCR
    return ocr_image(file_bytes, document_id)               # 画像ファイル
```

---

## 5. Vision API OCR（vision.py）

テキストレイヤーのないPDFや画像ファイルに対して、Google Cloud Vision API の `DOCUMENT_TEXT_DETECTION` を使用する。

### 処理フロー

1. **画像1枚の場合** (`ocr_image`): `ImageAnnotatorClient.document_text_detection()` を直接呼び出し
2. **PDFの場合** (`ocr_pdf`): PyMuPDF でページごとに300dpi PNG画像化 → `ocr_image` を各ページに適用

### 座標変換

Vision API の `boundingBox.vertices`（4頂点）を `BoundingBox(x, y, width, height)` に変換:

```python
def _vertices_to_bbox(vertices) -> BoundingBox:
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]
    x_min, y_min = min(xs), min(ys)
    return BoundingBox(x=x_min, y=y_min, width=max(xs) - x_min, height=max(ys) - y_min)
```

### WordResult の生成

Vision API のレスポンスは `pages > blocks > paragraphs > words > symbols` の階層構造。`symbols` の `text` を結合して1つの `WordResult` を生成し、`word.confidence` をそのまま使用する。

---

## 6. XLSX解析（xlsx.py）

```python
def extract_xlsx(file_bytes, document_id, sheet_name=None) -> OcrResult:
```

- `openpyxl` で `read_only=True, data_only=True` モードで開く（数式ではなく計算済み値を取得）
- シートごとに行をイテレーションし、セル値をタブ区切りで結合
- 各シートを1つの `PageResult` として扱い、テキスト先頭に `[Sheet: シート名]` を付与
- `sheet_name` 指定時は該当シートのみ処理
- `words` リストは空（座標情報なし）

---

## 7. DOCX解析（docx_text.py）

```python
def extract_docx(file_bytes, document_id) -> OcrResult:
```

- `python-docx` で文書を開く
- 段落（`doc.paragraphs`）のテキストを順に取得
- テーブル（`doc.tables`）の各行のセルをタブ区切りで結合
- 文書全体を1つの `PageResult`（`page_number=1`）として出力
- `words` リストは空（座標情報なし）

---

## 8. Geminiプロンプト構築（prompt_template.py）

### build_extraction_prompt

```python
def build_extraction_prompt(case_context: dict, document_descriptions: list[dict]) -> str:
```

`case_context` から `case_id`, `application_type`, `target_status` を、`document_descriptions` から書類一覧を受け取り、プロンプト文字列を生成する。

### プロンプトの構成

1. **役割定義**: 「日本の在留資格申請の構造化データ抽出AI」
2. **抽出対象**: 案件ID、申請種別、対象在留資格
3. **書類一覧**: ファイル名、役割（document_role）、document_id のリスト
4. **出力指示**: 3つのJSONオブジェクト（case_data / review / field_metadata）を含む単一JSON
5. **抽出の優先順位**: 身元情報 → 出入国歴 → 家族 → 学歴 → 職歴 → 雇用主 → 雇用条件 → activity_details → レビュー
6. **出力言語ルール**:
   - `case_data`: 原本の言語をそのまま使用
   - `review`: 日本語
   - `field_metadata`: 原文から直接引用
7. **レビュー方針（技人国）**: 職務と学歴の関連性、単純労働でないか、活動内容の具体性、書類の欠損・矛盾
8. **field_metadata 要件**: `case_data` の全フィールドに対応するエントリ必須。`source_refs` に `document_id`, `page`, `text_quote`, `confidence` を記録

---

## 9. Gemini API呼び出し（gemini.py）

モデル: `gemini-3-flash-preview`（環境変数 `GEMINI_MODEL` で変更可能）

### 3パターンの使い分け

| パターン | 関数 | 入力 | ユースケース |
|---|---|---|---|
| A: text_only | `extract_text_only()` | OCRテキスト＋テキスト書類 | OCR済みテキストのみで十分な場合 |
| B: pdf_direct | `extract_pdf_direct()` | PDFバイナリ＋テキスト書類 | Gemini にPDFを直接読ませる場合 |
| C: text_and_image | `extract_with_images()` | OCRテキスト＋画像バイナリ＋テキスト書類 | OCRテキストに加えて画像も渡す場合 |

3パターンとも、XLSX/DOCX由来のテキストは `text_contents: list[tuple[str, str]]`（document_id, テキスト）として渡せる。

### 共通処理（_call_gemini）

```python
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.0,
    max_output_tokens=65536,
)
```

- `response_mime_type="application/json"` で JSON 出力を強制
- `temperature=0.0` で決定論的な出力
- JSON パースに失敗した場合は `json_repair` ライブラリで修復を試みる
- `field_metadata` の正規化: `doc_id` → `document_id` への統一、`page` のデフォルト値設定
- `case_data` の全フィールドパスに対して `field_metadata` にエントリがなければ空の `source_refs` で補完

### _flatten_keys

`case_data` のネストされた dict/list 構造をドットパス表記（例: `applicant.education.0.school_name`）にフラット化するユーティリティ。`field_metadata` の補完に使用。

---

## 10. Bbox推定（bbox_locator.py）

フロントエンドで PDF 上にハイライト表示するために、特定フィールドの値がPDF上のどこにあるかを Gemini で推定する。

### 対象フィールド（BBOX_TARGET_FIELDS）

合計約20フィールド。主なものは:

- `applicant.name_roman`, `applicant.nationality_region`, `applicant.birth_date`, `applicant.passport.number`
- `employment.job_title`, `employment.monthly_salary`, `employment.work_location`
- `applicant.education.0.school_name`, `applicant.education.0.major_field`
- `employer.name`, `employer.capital_jpy`, `employer.representative_name`, `employer.industry_primary`, `employer.corporate_number`

### 処理フロー（locate_bboxes）

```python
def locate_bboxes(field_metadata: dict | list, pdf_bytes_map: dict[str, bytes]) -> dict:
```

1. `field_metadata` から対象フィールドの `source_refs` を走査
2. `(document_id, page)` のペアでグループ化し、各グループに `{field_path: text_quote}` を集約
3. 各ページを PyMuPDF で 300dpi PNG 画像に変換
4. `get_bboxes_for_page()` でページ画像と `field_quotes` を Gemini に送信
5. Gemini は `[y_min, x_min, y_max, x_max]`（0-1000 正規化座標）を返す
6. 結果を `field_metadata` の対応する `source_ref` に `bbox` として付与

### get_bboxes_for_page（gemini.py 内）

Gemini にページ画像を渡し、指定テキストの位置を特定させる。プロンプトは各テキストの field_path と text_quote を列挙し、JSON形式で `{field_path: [y_min, x_min, y_max, x_max]}` を返すよう指示する。

---

## 11. 具体例: オファーレターPDF（テキストレイヤーあり）の場合

テキストレイヤーを持つ通常のPDF（例: PCで作成されたオファーレター）の処理フロー。

### Step 1: ファイル受信

バックエンドがファイルアップロードを受け取り、`document_id` を発行。

### Step 2: テキストレイヤー判定

```
has_text_layer(pdf_bytes) → True（テキスト合計 >= 20文字）
```

### Step 3: PyMuPDF テキスト抽出

`pdf_text.extract_text()` を呼び出し:
- 各ページで `page.get_text("words")` → 単語ごとの座標付き `WordResult` を生成
- `page.get_text()` → ページ全体テキストを取得
- `OcrResult` にまとめて返す

### Step 4: Gemini プロンプト構築

`build_extraction_prompt()` で案件コンテキスト（案件ID、申請種別、在留資格）と書類一覧からプロンプトを生成。

### Step 5: Gemini 構造化抽出

`extract_text_only()` を使用（テキストのみで十分なため）:
- OCR結果テキストをプロンプトに結合
- Gemini API に送信（`temperature=0.0`, `response_mime_type="application/json"`）
- 返却 JSON から `case_data`, `review`, `field_metadata` を取得
- `field_metadata` を正規化（`doc_id` → `document_id` 統一、不足エントリ補完）

### Step 6: Bbox 付与

`locate_bboxes()` を呼び出し:
- 対象フィールド（氏名、国籍、生年月日、雇用条件等）の `source_refs` から `text_quote` を収集
- ページごとにグループ化し、300dpi PNG 画像に変換
- Gemini にページ画像とテキスト一覧を送信し、0-1000 正規化座標を取得
- `field_metadata` の `source_ref` に `bbox` を付与

### Step 7: フロントエンドへ返却

`ExtractionResult` に bbox 付き `field_metadata` を含めてレスポンス。フロントエンドはこの座標をもとに PDF ビューア上でハイライト表示する。

---

## 12. 具体例: スキャン画像PDF（テキストレイヤーなし）の場合

スキャンされた書類（例: 卒業証明書のスキャン画像をPDF化したもの）の処理フロー。

### Step 1: ファイル受信

同上。

### Step 2: テキストレイヤー判定

```
has_text_layer(pdf_bytes) → False（テキスト合計 < 20文字）
```

### Step 3: Vision API OCR

`vision.ocr_pdf()` を呼び出し:
- PyMuPDF でページごとに 300dpi PNG 画像を生成
- 各画像を `ocr_image()` に渡す
- Google Cloud Vision API `DOCUMENT_TEXT_DETECTION` で文字認識
- レスポンスの `pages > blocks > paragraphs > words > symbols` 階層から `WordResult` を生成
- 各 `WordResult` に Vision API の `confidence` と `bounding_box`（vertices → BoundingBox 変換）を付与
- `OcrResult` にまとめて返す

### Step 4 以降

Gemini プロンプト構築、構造化抽出、Bbox 付与は テキストレイヤーありの場合と同様。

ただし、Vision API OCR 経由の場合は `extract_with_images()`（パターンC）を使い、OCR テキストに加えて画像バイナリも Gemini に渡すことで、OCR の読み取りミスを画像で補完できる。

### テキストレイヤーありとの違いまとめ

| 項目 | テキストレイヤーあり | テキストレイヤーなし |
|---|---|---|
| テキスト抽出 | PyMuPDF 直接 | Vision API OCR（300dpi画像経由） |
| 単語座標の精度 | PDF座標そのまま（高精度） | Vision API の vertices から変換 |
| confidence | 常に 1.0 | Vision API の word.confidence |
| Gemini 呼び出し | パターンA（text_only）が典型 | パターンC（text_and_image）が典型 |
| 処理速度 | 高速 | Vision API 呼び出し分だけ遅い |
