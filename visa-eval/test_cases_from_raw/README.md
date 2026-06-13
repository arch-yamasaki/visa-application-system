# test_cases_from_raw

この配下は、申請人1人ずつの単票fixtureを置く場所です。

- `test_cases_from_raw/`: 申請人1人=1フォームの単票ケース。PDF/Excel読取、canonical v2 `case_data` 生成、backend generator由来の `application_data` 確認用。

`test_cases_from_raw/` の各ケースは、`scenario.json`、`input/document_manifest.json`、`output/output_manifest.json`、`expected/` を持ちます。

- `input/`: Gemini に渡す資料。元ファイル名は変更せず、どのファイルを使うかは `input/document_manifest.json` に書きます。
- `output/`: すでに入力済みの RASENS 申請書など、golden 作成・監査の根拠にする資料。Gemini 入力には使いません。
- `expected/`: golden 作成後に `*.golden.json` を置きます。golden 作成前のfixtureでは空でも構いません。

Gemini や比較スクリプトの実行結果は `test_cases_from_raw/` の中に置きません。`visa-eval/eval_runs/<run_id>/<case_id>/` に出します。

`expected/review.golden.json` は、Excel起点の scaffold を含む場合があります。抽出・投入の形を揃えるための期待値であり、レビュー判定の最終真実としてはPDF・会社資料・申請書類束を確認して更新します。

canonical v2移行後は、`expected/case_data.golden.json` を唯一の正本として扱います。`application_data` は `case_data` から比較時に backend generator で生成します。`expected/application_data.golden.json` が残っているケースでも、初期MVPの比較では使いません。`application.*`, top-level `passport.*`, `employment_conditions.*` などの旧pathはgoldenに残しません。

当面はAmit/Kushangの2ケースを優先します。`eval_config/suites/single_smoke.json` は旧13ケース拡張用の参考であり、active fixture が揃うまでは標準スイートとして扱いません。

eval の進め方と比較結果の読み方は `../../visa-app/docs/008_eval_workflow/README.md` を参照してください。`expected` と `expected` の比較は smoke check であり、Gemini抽出精度ではありません。実行結果の置き場所は `../eval_runs/README.md` を参照してください。
