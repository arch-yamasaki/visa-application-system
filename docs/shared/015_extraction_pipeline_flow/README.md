# 抽出パイプライン フロー図

visa-app バックエンドの抽出パイプライン全体を図解する。
コード上の関数名・ファイル名を併記し、実装に忠実に記述する。

---

## 全体フロー（AA図）

```
  POST /cases/{case_id}/extract
  (main.py: start_extraction)
         |
         v
  +-------------------------------+
  | case_ref.update               |
  | workflow_state = "extracting" |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | _extract_with_gemini()        |
  | (main.py)                     |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | GCS からドキュメント一括DL    |
  | file_entries[]                |
  +-------------------------------+
         |
         v
  +-----------------------------------------+
  | 拡張子で分類                            |
  | (main.py: _extract_with_gemini 内部)    |
  +-----------------------------------------+
         |
    +----+----+----+----+
    |    |    |    |    |
    v    v    v    v    v
  .pdf .xlsx .docx .png/.jpg
    |    |     |     |
    |    |     |     +---> image_entries[]
    |    |     |
    |    |     +---> extract_docx() -> text_contents[]
    |    |           (docx_text.py)
    |    |
    |    +---> extract_xlsx() -> text_contents[]
    |          (xlsx.py)
    |
    +---> pdf_contents[] + image_entries[]
         |
         v
  +-----------------------------------------+
  | パターン選択 (auto / 手動指定)          |
  | (詳細は「パターン選択ロジック」参照)    |
  +-----------------------------------------+
         |
    +----+----+---------+
    |         |         |
    v         v         v
 text_only pdf_direct text_and_image
    |         |         |
    v         v         v
  (後述)   (後述)    (後述)
    |         |         |
    +----+----+---------+
         |
         v
  +-------------------------------+
  | ExtractionResult              |
  |  .case_data                   |
  |  .display_case_data           |
  |  .review                      |
  |  .field_metadata              |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | Firestore 保存                |
  | case_ref.update({             |
  |   case_data,                  |
  |   review,                     |
  |   field_metadata,             |
  |   workflow_state:             |
  |     "needs_review"            |
  | })                            |
  +-------------------------------+
```

---

## パターン選択ロジック（AA図）

`_extract_with_gemini()` 内の `pattern == "auto"` 時の分岐:

```
  pattern == "auto" ?
         |
    +----+----+
    |         |
   YES        NO --> 指定された pattern をそのまま使用
    |
    v
  [file_entries に .pdf がある?]
         |
    +----+----+
    |         |
   YES        NO
    |         |
    |    [image_entries がある?]
    |         |
    |    +----+----+
    |    |         |
    |   YES        NO
    |    |         |
    v    v         v
 "pdf_direct"  "text_and_image"  "pdf_direct"
                                  (※テキストのみでも
                                   pdf_direct になる)
```

まとめ:
- PDFあり → `pdf_direct`
- PDFなし + 画像あり → `text_and_image`
- PDFなし + 画像なし → `pdf_direct` (pdf_contents は空だがそのまま通る)

---

## 各パターンの処理フロー（AA図）

### Pattern A: text_only

```
  image_entries[]
         |
         v
  +-------------------------------+
  | ocr_document() x N            |
  | (vision.py)                   |
  |   .pdf -> has_text_layer()?   |
  |     YES -> extract_text()     |
  |            (pdf_text.py)      |
  |     NO  -> ocr_pdf()          |
  |            (vision.py/        |
  |             Cloud Vision API) |
  |   .png/.jpg -> ocr_image()   |
  |            (Cloud Vision API) |
  +-------------------------------+
         |
         v
  ocr_results[] + text_contents[]
         |
         v
  +-------------------------------+
  | extract_text_only()           |
  | (gemini.py)                   |
  |                               |
  | build_extraction_prompt()     |
  | + OCRテキスト                 |
  | + テキスト書類(xlsx/docx)     |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | _call_gemini()                |
  | contents=[], prompt=全テキスト|
  | (テキストのみ、画像なし)      |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | _build_extraction_result()    |
  +-------------------------------+
```

### Pattern B: pdf_direct (メインパターン)

```
  pdf_contents[] + text_contents[]
         |
         v
  +-------------------------------+
  | extract_pdf_direct()          |
  | (gemini.py)                   |
  |                               |
  | parts[] を構築:               |
  |   テキスト書類 → 文字列Part   |
  |   PDF → Part.from_bytes()    |
  |         (mime: application/   |
  |          pdf)                 |
  |   + "(document_id: xxx)"     |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | _call_gemini()                |
  | contents=parts[], prompt=抽出 |
  | 指示                          |
  | (PDFバイナリ直接送信)         |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | _build_extraction_result()    |
  +-------------------------------+
         |
         v
  +=================================+
  | locate_bboxes()                 |
  | (bbox_locator.py)               |
  | 詳細は「bbox処理の詳細フロー」 |
  +=================================+
```

### Pattern C: text_and_image

```
  image_entries[]
         |
         v
  +-------------------------------+
  | ocr_document() x N            |
  | (vision.py)                   |
  +-------------------------------+
         |
         v
  ocr_results[]
         |
  +------+------+
  |             |
  v             v
  text_contents[]  image_contents[]
         |             |
         v             v
  +-------------------------------+
  | extract_with_images()         |
  | (gemini.py)                   |
  |                               |
  | parts[] を構築:               |
  |   テキスト書類 → 文字列Part   |
  |   OCRテキスト → 文字列Part    |
  |   画像/PDF → Part.from_bytes()|
  |     PNG → image/png           |
  |     JPG → image/jpeg          |
  |   + "(document_id: xxx)"     |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | _call_gemini()                |
  | contents=parts[], prompt=抽出 |
  | 指示                          |
  +-------------------------------+
         |
         v
  +-------------------------------+
  | _build_extraction_result()    |
  +-------------------------------+
         |
         v
  [pdf_contents がある?]
    +----+----+
    |         |
   YES        NO --> bbox処理スキップ
    |
    v
  +=================================+
  | locate_bboxes()                 |
  +=================================+
```

---

## bbox処理の詳細フロー（AA図）

`bbox_locator.py: locate_bboxes()`

```
  field_metadata (dict)
  pdf_bytes_map {doc_id: bytes}
         |
         v
  +--------------------------------------+
  | _map_field_metadata()                |
  | list形式ならdict形式に正規化         |
  +--------------------------------------+
         |
         v
  +--------------------------------------+
  | BBOX_TARGET_FIELDS (22フィールド)    |
  | でフィルタ                           |
  |                                      |
  | 対象:                                |
  |   applicant.name_roman               |
  |   applicant.nationality              |
  |   applicant.date_of_birth            |
  |   applicant.passport_number          |
  |   employment_conditions.job_title    |
  |   employment_conditions.duties       |
  |   employment_conditions.monthly_     |
  |     salary / annual_salary / bonus   |
  |   employment_conditions.work_        |
  |     location / working_hours /       |
  |     joining_date / holidays /        |
  |     insurance / contract_period /    |
  |     contract_type                    |
  |   education.0.school_name            |
  |   education.0.major                  |
  |   employer.company_name              |
  |   employer.capital                   |
  |   employer.representative_name       |
  |   employer.business_category         |
  |   employer.business_type             |
  |   employer.corporate_number          |
  +--------------------------------------+
         |
         v
  +--------------------------------------+
  | source_refs から                     |
  | (document_id, page) でグループ化     |
  |                                      |
  | page_groups:                         |
  |   {(doc_id, page): {field: quote}}   |
  |                                      |
  | ※ PDFのみ対象                        |
  | ※ text_quote が空なら除外           |
  +--------------------------------------+
         |
         v
  +--------------------------------------+
  | 各ページのPNG画像レンダリング        |
  | (逐次処理)                           |
  |                                      |
  | pymupdf で page.get_pixmap(dpi=300)  |
  | -> PNG bytes                         |
  +--------------------------------------+
         |
         v
  +==============================================+
  ||  ThreadPoolExecutor (max_workers=4)        ||
  ||                                            ||
  ||  ページごとに並列:                         ||
  ||                                            ||
  ||  +--------------------------------------+  ||
  ||  | get_bboxes_for_page()                |  ||
  ||  | (gemini.py)                          |  ||
  ||  |                                      |  ||
  ||  | 入力:                                |  ||
  ||  |   page_image (PNG bytes)             |  ||
  ||  |   {field_path: text_quote}           |  ||
  ||  |                                      |  ||
  ||  | Gemini API 呼び出し:                 |  ||
  ||  |   model: BBOX_MODEL_NAME             |  ||
  ||  |   contents: [image_part, prompt]     |  ||
  ||  |   response_mime: application/json    |  ||
  ||  |   temperature: 0.0                   |  ||
  ||  |                                      |  ||
  ||  | 出力:                                |  ||
  ||  |   {field_path:                       |  ||
  ||  |     [y_min, x_min, y_max, x_max]}   |  ||
  ||  |   座標: 0-1000 正規化               |  ||
  ||  +--------------------------------------+  ||
  ||                                            ||
  +==============================================+
         |
         v
  +--------------------------------------+
  | 結果を field_metadata に反映         |
  |                                      |
  | source_refs[].bbox = {               |
  |   y_min, x_min, y_max, x_max        |
  | }                                    |
  +--------------------------------------+
         |
         v
  field_metadata (bbox付き) を返却
```

---

## データフロー（AA図）

入力から出力までのデータ変換の流れ:

```
  [入力: GCS上のドキュメントバイナリ]
         |
         |  .pdf    .xlsx         .docx        .png/.jpg
         |   |       |             |              |
         v   v       v             v              v
  +------+  extract_xlsx()  extract_docx()  (そのまま)
  | PDF  |  -> OcrResult    -> OcrResult    -> image bytes
  | bytes|  -> text str     -> text str
  +------+
         |
         v
  [中間データ]
    pdf_contents:  [(doc_id, pdf_bytes), ...]
    text_contents: [(doc_id, text_str), ...]
    image_entries: [(doc_id, fname, bytes), ...]
         |
         v
  [Gemini 入力 (parts)]
    Pattern A: テキスト文字列のみ (contents=[])
    Pattern B: Part.from_bytes(pdf) + テキスト文字列
    Pattern C: Part.from_bytes(image) + OCRテキスト + テキスト文字列
         |
         v
  [Gemini 出力: JSON]
    {
      "case_data": { ... FieldValue構造 ... },
      "review": { ... }
    }
         |
         v
  [後処理 (_build_extraction_result)]
    1. _unflatten_field_values()   -- compact形式 → source_refs形式
    2. _normalize_employment_keys() -- employment_terms → employment_conditions
    3. _normalize_corporate_number() -- ハイフン除去
    4. _is_new_format() で判定
       YES (新形式):
         _extract_field_metadata()   -- FieldValue → field_metadata 自動生成
         _extract_display_values()   -- FieldValue → 表示用case_data
       NO (旧形式):
         _map_field_metadata()       -- list→dict 正規化
    5. _normalize_source_refs_in_metadata() -- doc_id→document_id, page正規化
         |
         v
  [ExtractionResult]
    .case_data          -- 生のFieldValue構造 (新形式)
    .display_case_data  -- value のみ (表示用、Firestore保存用)
    .review             -- レビュー情報
    .field_metadata     -- {field_path: {source_refs, confidence, ...}}
         |
         v
  [bbox後処理] (pdf_direct / text_and_image のみ)
    locate_bboxes() で field_metadata に bbox 座標追加
         |
         v
  [Firestore 保存]
    case_data       = display_case_data (表示用)
    review          = review
    field_metadata  = field_metadata (bbox付き)
    workflow_state  = "needs_review"
```

---

## Gemini API 呼び出し回数まとめ

| フェーズ | 関数 | 回数 | 並列 | 用途 |
|---|---|---|---|---|
| メイン抽出 | `_call_gemini()` | 1回 | - | case_data + review の構造化抽出 |
| bbox座標推定 | `get_bboxes_for_page()` | ページ数に依存 (典型: 3-6回) | 最大4並列 (`ThreadPoolExecutor`) | 対象22フィールドの座標推定 |
| **合計** | | **4-7回** (典型) | | |

補足:
- bbox は `pdf_direct` と `text_and_image` (PDFあり時) のみ実行される
- `text_only` パターンでは bbox 処理はスキップされるため、Gemini 呼び出しは1回のみ
- bbox の並列数は環境変数 `BBOX_MAX_WORKERS` で制御 (デフォルト: 4)
- メイン抽出のモデルは `GEMINI_MODEL` (デフォルト: `gemini-3-flash-preview`)
- bbox のモデルは `GEMINI_BBOX_MODEL` (デフォルト: `gemini-3-flash-preview`)

---

## OCR分岐の詳細 (vision.py: ocr_document)

`text_only` / `text_and_image` パターンで使用される OCR の内部分岐:

```
  ocr_document(file_bytes, file_name, document_id)
         |
    [拡張子判定]
         |
    +----+----+
    |         |
   .pdf    .png/.jpg/.jpeg
    |         |
    v         v
  has_text_layer()?     ocr_image()
  (pdf_text.py)         (Cloud Vision API)
    |                   DOCUMENT_TEXT_DETECTION
  +-+--+
  |    |
 YES   NO
  |    |
  v    v
extract_text()    ocr_pdf()
(pdf_text.py      (vision.py)
 PyMuPDF          ページごとに
 テキスト         画像化(300dpi)
 レイヤー)        -> ocr_image()
```
