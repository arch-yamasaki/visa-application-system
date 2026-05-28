# rasens-autofill/data

このディレクトリは、在留申請オンラインシステム入力支援のフォーム台帳、変換ルール、デモfixture、生成物を置く場所です。

実運用案件の保存先は visa-app の Firestore `cases` コレクションです。ここに実案件由来の `case_data` や個人情報入り投入JSONを置きません。

## データの流れ

実運用では、`case_data` から投入JSONを作る処理は visa-app backend の `/application-data` に寄せます。Chrome拡張は backend が返す `rows` を入力するだけです。

このディレクトリの mapping と generated JSON は、設計資産・合成デモ・検証用です。実案件の正本や本番投入ロジックの置き場所ではありません。

```text
reference_form.html
  -> form_definitions/rasens_offer_fields.json
  -> mappings/rasens_offer_mapping_v2.json

cases/demo_case_data.json
  + mappings/rasens_offer_mapping_v2.json
  -> generated/demo_application_data.json
```

## ディレクトリ

- `cases/`: 合成デモ・fixture用の `case_data`。実運用案件の正本ではない。
- `form_definitions/`: 入管オンライン申請フォームの項目台帳。`reference_form.html` から抽出したもの。
- `mappings/`: 正規 `case_data` からフォーム入力項目への変換ルール。
- `schemas/`: AIレビュー出力と入力資料manifestの評価補助用 JSON Schema。
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

`mappings/` では、17.2〜17.4 のような条件付き項目を `visible_when`、21.2〜21.8 や職歴01〜06のような繰り返し項目を `groups` で表します。`field_id` や `field_name` は画面依存なので、案件正本のキーには使いません。`visible_when` と `transform` の評価は backend generator が担当し、Chrome拡張には持たせません。

`mappings/rasens_offer_mapping_v2.json` は canonical v2 のMVP自動投入対象です。`form_definitions/rasens_offer_fields.json` の274行台帳を正とし、自動投入しない行は今後 `manual`, `settings`, `derived`, `unsupported`, `future` などの扱いを付けていきます。

代理人は `proxy` として案件ごとに扱います。取次者は `intermediary` として、太田さん側の申請アカウントを持つ申請会社情報を固定設定値から注入します。

## デモ生成

リポジトリルートから実行する。

```bash
python visa-eval/scripts/build_application_data.py \
  rasens-autofill/data/cases/demo_case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping_v2.json \
  rasens-autofill/data/generated/demo_application_data.json
```
