# test_cases_from_raw

この配下は、申請人1人ずつの単票fixtureを置く場所です。

- `test_cases_from_raw/`: 申請人1人=1フォームの単票ケース。PDF/Excel読取、canonical v2 `case_data` 生成、backend generator由来の `application_data` 確認用。

`test_cases_from_raw/` の各ケースは、`scenario.json`、`input/document_manifest.json`、`output/output_manifest.json`、`expected/`、`expected_verified/` を持ちます。

- `input/`: Gemini に渡す資料。元ファイル名は変更せず、どのファイルを使うかは `input/document_manifest.json` に書きます。
- `output/`: すでに入力済みの RASENS 申請書など、golden 作成・監査の根拠にする資料。Gemini 入力には使いません。
- `expected/`: 旧golden。履歴として変更しません。
- `expected_verified/`: 現在の比較に使う確認済みgoldenと `golden_manifest.json`。AI入力には渡しません。

Gemini や比較スクリプトの実行結果は `test_cases_from_raw/` の中に置きません。`visa-eval/eval_runs/<run_id>/<case_id>/` に出します。

`expected/review.golden.json` は、Excel起点の scaffold を含む場合があります。抽出・投入の形を揃えるための期待値であり、レビュー判定の最終真実としてはPDF・会社資料・申請書類束を確認して更新します。

現在の比較では、`expected_verified/case_data.golden.json` を値の正本、`golden_manifest.json` を採点範囲の正本として扱います。旧 `expected/` は移行前データとして残します。`application_data` は `case_data` から比較時に backend generator で生成します。

現在はactive 8ケースを、原資料付きの主要fixtureとして扱います。既存2ケースは旧 `expected/` と新 `expected_verified/` を保持し、新規6ケースは旧 `expected/` を作らず、新しい比較用の `expected_verified/` だけを保持します。全8ケースが scoring ready です。

提出済み申請書PDFに RASENS 申請書ページと添付資料ページが混在する場合は、物理分割したうえで RASENS 側を `output/rasens_application/`、添付資料側を `input/submitted_application_attachments/` に置きます。`raw/` に別置きされた申請人別の未添付資料がある場合は、申請添付ではなくても抽出根拠になり得るため `input/files/` に置き、`document_manifest.json` で `use_as_input: true` とします。

eval の進め方と比較結果の読み方は `../../visa-app/docs/008_eval_workflow/README.md` を参照してください。`expected` と `expected_verified` の比較は smoke check であり、Gemini抽出精度ではありません。実行結果の置き場所は `../eval_runs/README.md` を参照してください。
