# fixtures_single

この配下は、申請人1人ずつの単票fixtureを置く場所です。

- `fixtures_single/`: 申請人1人=1フォームの単票ケース。PDF/Excel読取、`case_data` 生成、`application_data.golden.json` の確認用。

`fixtures_single/` の各ケースは、`scenario.json`、`input/document_manifest.json`、`expected/*.golden.json`、`generated/` を持ちます。

`expected/review.golden.json` は、Excel起点の scaffold を含む場合があります。抽出・投入の形を揃えるための期待値であり、レビュー判定の最終真実としてはPDF・会社資料・申請書類束を確認して更新します。

単票の評価をすぐ回す場合は `eval/suites/single_smoke.json` を使います。`fixture_family` は `single` です。
