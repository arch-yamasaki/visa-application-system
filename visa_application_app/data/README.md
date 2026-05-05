# visa_application_app/data

このディレクトリは、在留申請オンラインシステム入力支援のデータ正本と生成物を置く場所です。

## データの流れ

```text
reference_form.html
  -> form_definitions/rasens_offer_fields.json
  -> mappings/rasens_offer_mapping.json

cases/demo_case_data.json
  + mappings/rasens_offer_mapping.json
  -> generated/demo_application_data.json
```

## ディレクトリ

- `schemas/`: 正規データのJSON Schema。
- `cases/`: 案件単位の正規 `case_data`。AI/OCR/人手補正の保存先。
- `form_definitions/`: 入管オンライン申請フォームの項目台帳。`reference_form.html` から抽出したもの。
- `mappings/`: 正規 `case_data` からフォーム入力項目への変換ルール。
- `generated/`: Chrome拡張に渡す投入用JSONなど、再生成できる派生物。
- `test_cases/`: AIエージェント評価用のraw資料、入力リスト、期待アウトプット、評価スイート。
- `pdf_pages/`, `reference_form.html`: 参照元キャプチャ。

## 正本

案件の正本は `cases/*case_data.json` です。`generated/*application_data.json` は拡張入力用の派生物で、手編集を前提にしません。

フォーム項目台帳の正本は `form_definitions/rasens_offer_fields.json` です。サイト構造が変わった場合は、この台帳と `mappings/` を更新します。

`mappings/` では、17.2〜17.4 のような条件付き項目を `visible_when`、21.2〜21.8 や職歴01〜06のような繰り返し項目を `groups` で表します。`field_id` や `field_name` は画面依存なので、案件正本のキーには使いません。

## デモ生成

```bash
python3 visa_application_app/scripts/build_application_data.py \
  visa_application_app/data/cases/demo_case_data.json \
  visa_application_app/data/mappings/rasens_offer_mapping.json \
  visa_application_app/data/generated/demo_application_data.json
```
