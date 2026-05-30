# test_cases_from_raw

この配下は、申請人1人ずつの単票fixtureを置く場所です。

- `test_cases_from_raw/`: 申請人1人=1フォームの単票ケース。PDF/Excel読取、canonical v2 `case_data` 生成、backend generator由来の `application_data` 確認用。

`test_cases_from_raw/` の各ケースは、`scenario.json`、`input/document_manifest.json`、`expected/*.golden.json`、`generated/` を持ちます。

`expected/review.golden.json` は、Excel起点の scaffold を含む場合があります。抽出・投入の形を揃えるための期待値であり、レビュー判定の最終真実としてはPDF・会社資料・申請書類束を確認して更新します。

canonical v2移行後は、`expected/case_data.golden.json` を唯一の正本として扱います。`application_data` は `case_data` から比較時に backend generator で生成します。`expected/application_data.golden.json` が残っているケースでも、初期MVPの比較では使いません。`application.*`, top-level `passport.*`, `employment_conditions.*` などの旧pathはgoldenに残しません。

単票の評価をすぐ回す場合は `eval_config/suites/single_smoke.json` を使います。`fixture_family` は `single` です。
