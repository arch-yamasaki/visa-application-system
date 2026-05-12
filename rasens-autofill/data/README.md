# rasens-autofill/data

このディレクトリは、在留申請オンラインシステム入力支援のデータ正本と生成物を置く場所です。  
ただし、`visa-eval/` はリポジトリ直下へ移動済みです。

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

- `schemas/`: 正規データ、AIレビュー出力、入力資料manifestのJSON Schema。
- `cases/`: 案件単位の正規 `case_data`。AI/OCR/人手補正の保存先。
- `form_definitions/`: 入管オンライン申請フォームの項目台帳。`reference_form.html` から抽出したもの。
- `mappings/`: 正規 `case_data` からフォーム入力項目への変換ルール。
- `generated/`: Chrome拡張に渡す投入用JSONなど、再生成できる派生物。
- `visa-eval/`: 以前はここにあったが、現在はリポジトリ直下の `visa-eval/` に移動済み。
- `reference_form.html`: フォーム項目台帳を作るための参照元HTML。

## Git管理

この配下は、実PIIを入れない設計資産として git 管理する。

- 管理する: `schemas/`, `cases/demo_case_data.json`, `form_definitions/`, `mappings/`, `generated/demo_application_data.json`, `reference_form.html`
- 管理しない: 一時CSV、PDF/画像キャプチャ、実案件由来の `case_data`, 個人情報入りの投入JSON

実案件でCodex検証するデータは、リポジトリ直下の `visa-eval/` に置く。

## 正本

案件の正本は `cases/*case_data.json` です。`generated/*application_data.json` は拡張入力用の派生物で、手編集を前提にしません。

フォーム項目台帳の正本は `form_definitions/rasens_offer_fields.json` です。サイト構造が変わった場合は、この台帳と `mappings/` を更新します。

`mappings/` では、17.2〜17.4 のような条件付き項目を `visible_when`、21.2〜21.8 や職歴01〜06のような繰り返し項目を `groups` で表します。`field_id` や `field_name` は画面依存なので、案件正本のキーには使いません。

現時点の `mappings/rasens_offer_mapping.json` は主要項目だけの初期版です。フォーム台帳全体を網羅しているわけではなく、代理人・取次者、受領方法、学歴区分、専攻、在日親族詳細、職歴複数件などは追加対応が必要です。

## デモ生成

```bash
python3 rasens-autofill/scripts/build_application_data.py \
  rasens-autofill/data/cases/demo_case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping.json \
  rasens-autofill/data/generated/demo_application_data.json
```
