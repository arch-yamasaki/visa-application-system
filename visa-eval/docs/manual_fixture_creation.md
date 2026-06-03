# Manual Fixture Creation

`test_cases_from_raw/` のfixtureは、実案件由来の restricted test data です。
自動分類で増やさず、申請人ごとに手動で作ります。

## 基本方針

- `raw/` は受領した原本置き場です。加工しません。
- `test_cases_from_raw/<case_id>/<applicant_id>/` に、評価用に整理したコピーや分割PDFを置きます。
- 入力ファイルの実ファイル名は、原則として元名のままにします。
- Gemini に渡すファイルは `input/document_manifest.json` で明示します。
- RASENS出力済み申請書などの正解監査資料は `output/` に置き、Gemini には渡しません。
- `expected/` は golden 作成後に使います。fixture作成直後は空でも構いません。

## ディレクトリ構成

```text
visa-eval/test_cases_from_raw/<case_id>/<applicant_id>/
  scenario.json
  input/
    document_manifest.json
    files/
      ...Gemini入力資料...
    submitted_application_attachments/
      ...申請書PDFの添付資料ページなど...
  output/
    output_manifest.json
    rasens_application/
      ...RASENS入力済み申請書PDF...
  expected/
  generated/
```

## 申請書PDFを分ける理由

提出済み申請書PDFには、性質の違うページが混ざることがあります。

```text
1-10ページ目   RASENSに入力済みの申請書
              -> output/rasens_application/
              -> golden 作成・監査の根拠
              -> Gemini入力にはしない

11ページ目以降 旅券、証明書、添付資料など
              -> input/submitted_application_attachments/
              -> Gemini入力にできる
```

同じ元PDFから切り出した場合でも、前半と後半は役割を分けます。
前半は `output_manifest.json`、後半は `input/document_manifest.json` に書きます。

## manifest の書き方

`input/document_manifest.json` の `path` は repo root からの相対パスにします。
これは `prepare_blind_eval_run.py` が `ROOT / doc["path"]` として読むためです。

fixture本体では元ファイル名を維持します。`prepare_blind_eval_run.py` が作る一時runでは、資料コピー名が `doc_001.pdf` のように変わりますが、`document_manifest.blind.json` の `file_name` には元ファイル名を残します。

```json
{
  "document_id": "submitted_application_attachments",
  "path": "visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/input/submitted_application_attachments/TAMANG AMIT様.pdf",
  "file_name": "TAMANG AMIT様.pdf",
  "extension": "pdf",
  "document_role": "submitted_application_bundle",
  "use_as_input": true,
  "origin_path": "visa-eval/raw/申請書類/A社（１回目申請）/TAMANG AMIT様.pdf",
  "origin_pages": "11-20",
  "derivation_type": "page_split"
}
```

`output/output_manifest.json` は、golden 作成・監査で見る資料を示します。

```json
{
  "document_id": "rasens_application_output",
  "path": "visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/output/rasens_application/TAMANG AMIT様.pdf",
  "file_name": "TAMANG AMIT様.pdf",
  "document_role": "submitted_application_rasens_output",
  "use_as_input": false,
  "purpose": "golden_audit",
  "origin_path": "visa-eval/raw/申請書類/A社（１回目申請）/TAMANG AMIT様.pdf",
  "origin_pages": "1-10",
  "derivation_type": "page_split"
}
```

## 作成手順

1. `raw/` から対象ケースと申請人を確認する。
2. `test_cases_from_raw/<case_id>/<applicant_id>/` を作る。
3. Gemini入力資料を `input/files/` にコピーする。
4. 提出済み申請書PDFのうち、RASENS申請書ページを `output/rasens_application/` に切り出す。
5. 同じPDFの添付資料ページを、必要に応じて `input/submitted_application_attachments/` に切り出す。
6. `scenario.json`、`input/document_manifest.json`、`output/output_manifest.json` を書く。
7. `--dry-run` で、Geminiへ送る資料数と容量を確認する。
8. `prepare_blind_eval_run.py` で blind run が作れることを確認する。

確認コマンド:

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py \
  visa-eval/test_cases_from_raw/<case_id>/<applicant_id> \
  --dry-run

visa-app/backend/.venv/bin/python visa-eval/scripts/prepare_blind_eval_run.py \
  visa-eval/test_cases_from_raw/<case_id>/<applicant_id>
```

## Golden 作成は別工程

fixture作成では、`expected/*.golden.json` を無理に作りません。
まず入力資料と正解監査資料を分け、blind run / Gemini bytes eval が動く状態にします。

golden 作成では、`output/rasens_application/` と入力資料を見ながら、人が `expected/case_data.golden.json` を作ります。
詳しい進め方は `../../visa-app/docs/008_eval_workflow/README.md` を参照します。
