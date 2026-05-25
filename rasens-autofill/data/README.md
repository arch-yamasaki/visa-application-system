# rasens-autofill/data

このディレクトリは、在留申請オンラインシステム入力支援のフォーム台帳、変換ルール、デモfixture、生成物を置く場所です。

実運用案件の保存先は visa-app の Firestore `cases` コレクションです。ここに実案件由来の `case_data` や個人情報入り投入JSONを置きません。

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

- `schemas/`: case_data、AIレビュー出力、入力資料manifestのJSON Schema。現行 `case_data.schema.json` は canonical v2 設計前の部分スキーマ。
- `cases/`: 合成デモ・fixture用の `case_data`。実運用案件の正本ではない。
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

## 正本と派生物

案件の正本はこのディレクトリではなく、visa-app の Firestore `cases/{case_id}` です。今後の canonical schema 整備では、Firestore `case_data` を値だけの正本、`field_metadata` と `review` を top-level の関連データとして扱います。

`cases/demo_case_data.json` は合成デモfixtureです。`generated/*application_data.json` は拡張入力用の派生物で、手編集を前提にしません。

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
