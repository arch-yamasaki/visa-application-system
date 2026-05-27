# Application Data API

## 目的

Chrome拡張は RASENS DOM に値を入力するだけにし、`case_data` の解釈や `rasens_offer_mapping_v2.json` の評価は backend 側に寄せます。

旧 `/cases/{case_id}/autofill-data` は削除済みです。現在は backend が `/cases/{case_id}/application-data` で投入行を返します。

このAPIの責務分離は次の通りです。

| 要素 | 責務 |
|---|---|
| `case_data` | 案件の正本。RASENS物理IDやselect値は持たない |
| `form_definitions` | RASENSフォーム274行の物理台帳。正本は `rasens_offer_fields.json` |
| `mapping` | canonical path と RASENS物理項目の対応。backendだけが読む |
| backend generator | `transform`、`visible_when`、固定値、設定値、手入力要否を評価し、`rows` を生成する |
| Chrome拡張 | backendが返した `rows` をRASENS DOMへ入力し、成功/失敗を表示する |

## 新API

```http
GET /cases/{case_id}/application-data
```

## Response

```json
{
  "schema_version": "1.0",
  "case_id": "case_xxx",
  "workflow_state": "extracted",
  "fillable": true,
  "mapping_version": "0.1.0",
  "form_definition": "rasens_offer_fields.json",
  "warnings": [],
  "summary": {
    "rows_total": 55,
    "rows_fillable": 48,
    "rows_skipped_empty": 7,
    "manual_required": 3
  },
  "rows": []
}
```

| field | 役割 |
|---|---|
| `schema_version` | application-data API response の版 |
| `case_id` | 対象ケース |
| `workflow_state` | 現在の状態 |
| `fillable` | Chrome拡張で投入してよい状態か |
| `mapping_version` | 使用した mapping の版 |
| `form_definition` | 使用したフォーム台帳 |
| `warnings` | workflowなど、Chrome拡張の投入可否に関する警告 |
| `summary` | 生成結果の概要 |
| `rows` | Chrome拡張が入力する行 |

`workflow_state` が入力不可状態でも、preview目的で `rows` を返してよいです。ただし `fillable` は `false` にし、Chrome拡張側で警告を出します。

投入可能扱い:

- `extracted`
- `needs_review`（移行互換）
- `ready_to_fill`（移行互換）

## Row schema

```json
{
  "section": "身分事項",
  "form_order": 19,
  "display_no": "12",
  "label": "入国予定年月日",
  "canonical_path": "entry_plan.planned_entry_date",
  "source_paths": ["entry_plan.planned_entry_date"],
  "field_name": "item[22].textData",
  "field_id": "switch_256118",
  "input_type": "text",
  "display_value": "2026-06-01",
  "fill_value": "20260601",
  "source_page": "case_data",
  "confidence": "generated",
  "required": true,
  "manual_required": false,
  "notes": ""
}
```

| field | 必須 | 役割 |
|---|---:|---|
| `section` | yes | RASENS上のセクション |
| `form_order` | yes | フォーム台帳内の出現順。previewや検証の並びに使う |
| `display_no` | no | RASENS画面に表示される番号・見出し。人間向けの参考情報でありIDではない |
| `label` | yes | 人間向けラベル |
| `canonical_path` | no | 主に参照する `case_data` path。固定値や派生値では空の場合がある |
| `source_paths` | no | 値の生成に使った `case_data` path。複数fieldから派生する場合に使う |
| `field_name` | no | RASENS HTML name。DOM投入先の特定用で、業務上のIDではない |
| `field_id` | no | RASENS HTML id。DOM投入先の特定用で、業務上のIDではない |
| `input_type` | yes | `text`, `select`, `radio`, `checkbox`, `textarea`, `file` |
| `display_value` | yes | UI表示値 |
| `fill_value` | yes | DOM投入値 |
| `source_page` | no | 生成元の大分類。例: `case_data`, `fixed`, `derived`, `settings` |
| `confidence` | no | 値の確度や生成種別。例: `extracted`, `reviewed`, `generated`, `manual` |
| `required` | no | RASENS上の必須。業務上の不足確認とは分ける |
| `manual_required` | no | 自動投入せず人手対応が必要 |
| `notes` | no | 生成時の補足 |

Chrome拡張が fillable row で最低限必要とするのは、`field_name` または `field_id` の少なくとも一方、`input_type`, `fill_value`, `label` です。それ以外は preview / diagnostics 用です。

`display_no` は入力先の識別に使いません。セクションをまたいで同じ番号が再登場し、繰り返し項目でも重複するためです。

`form_order` は `form_definition` と `mapping_version` の組み合わせの中でのみ意味を持ちます。フォーム台帳が更新された場合は、`form_order` も再生成します。

## backend の生成責務

backend は次を行います。

1. Firestore `case_data` を読む。
2. `rasens_offer_fields.json` からフォーム制約を読む。
3. canonical v2 用に作り直した mapping を読む。
4. mapping の `field_id` / `field_name` がフォーム制約と一致することを検証する。
5. `visible_when` を評価する。
6. `transform` を適用する。
7. 取次者などの固定設定値を注入する。
8. 空値・非該当値を skip する。
9. `application_data.rows` を返す。

`transform` と `visible_when` は backend にだけ置きます。Chrome拡張、評価CLI、デモ生成で同じ処理を再実装しません。評価CLIが必要な場合も、backend generator の共通ロジックを呼ぶ形にします。

MVPでは、RASENS入力で必ず選択が必要な一部項目を backend 側で派生・既定値補完します。これはGemini抽出の代替ではなく、抽出結果が空のときにフォーム投入を進めるための初期値です。レビュー画面で人が確認・修正する前提です。

| canonical path | 補完ルール |
|---|---|
| `entry_plan.planned_port` | 勤務先所在地から空港を推測。東京圏は羽田、北関東等は成田、中部は中部国際、関西は関西国際、北海道は新千歳、中国地方は広島、九州は福岡 |
| `entry_plan.planned_period_years` | 空なら `5` |
| `entry_plan.planned_period_months` | 空なら `0` |
| `applicant.family.has_accompanying_members` | 空なら `false` |
| `applicant.immigration_history.has_entries` | 空なら `false` |
| `applicant.immigration_history.prior_coe_applications.has_history` | 空なら `false` |
| `applicant.immigration_history.criminal_record` | 空なら `false` |
| `applicant.immigration_history.deportation_or_departure_order` | 空なら `false` |
| `employer.has_corporate_number` | `employer.corporate_number` があれば `true`、なければ `false` |
| `employment.contract_type` | 空なら `雇用 Employment` |
| `employment.employment_period_type` | 空なら `定めあり Fixed` |
| `employment.employment_period_years` | 空なら `1` |
| `employment.employment_period_months` | 空なら `0` |
| `applicant.education.0.country_type` | 空なら学校名・学歴から本邦/外国を推測。海外大学は `外国 Foreign country` |
| `applicant.education.0.level` | `Bachelor`, `University`, `学士` 等を `大学 Bachelor` へ寄せる |
| `applicant.education.0.major_field` | `Architectural Engineering` 等を RASENS 選択肢の `工学 Engineer` へ寄せる |
| `proxy.*` | 空なら勤務先会社情報から `name`, `postal_code`, `address`, `phone` を初期化し、本人との関係は `所属機関等契約先` |

`required` の意味は分けます。`rows[].required` は `form_definitions` 由来のRASENS入力制約を表し、業務上の不足や人手確認は `review.missing_items`, `review.validation_errors`, `manual_required` で表します。固定設定値で埋まる取次者は、Gemini抽出requiredにはしません。

Chrome拡張への投入は、部分入力を基本許可します。RASENS上の必須項目が未入力でも、取得できた行は投入し、空欄はレビュー画面とRASENS画面で人が確認・補完します。`fillable=false` は `draft`、`extracting`、`failed` など、まだ投入対象にすべきでない workflow 状態を止めるために使い、必須不足の validation gate には使いません。

`intermediary` は取次者で、太田さん側の申請アカウントを持つ申請会社情報を設定から注入します。案件書類やGemini抽出から作る値ではありません。Firestore `settings.intermediary` があればそれを使い、なければ Cloud Run 環境変数 `INTERMEDIARY_NAME`, `INTERMEDIARY_POSTAL_CODE`, `INTERMEDIARY_ADDRESS`, `INTERMEDIARY_ORGANIZATION`, `INTERMEDIARY_PHONE` から注入します。

本番では実値をrepoに書かず、Secret Manager または Cloud Run 環境変数で設定します。Firestore `settings.intermediary` があるケースでは Firestore の値を優先し、ないケースでは Cloud Run の固定設定を使います。

```bash
gcloud run services update visa-app \
  --region asia-northeast1 \
  --project visa-codex-mvp \
  --update-secrets="INTERMEDIARY_NAME=INTERMEDIARY_NAME:latest,INTERMEDIARY_POSTAL_CODE=INTERMEDIARY_POSTAL_CODE:latest,INTERMEDIARY_ADDRESS=INTERMEDIARY_ADDRESS:latest,INTERMEDIARY_ORGANIZATION=INTERMEDIARY_ORGANIZATION:latest,INTERMEDIARY_PHONE=INTERMEDIARY_PHONE:latest"
```

有無系は、レビューUIやFirestore上で `true`, `"true"`, `"有"` のように表記が揺れても、`application-data` 生成時に同じ意味として扱います。これにより、`visible_when` を持つ条件付き項目が文字列/booleanの違いだけで消えないようにします。

`proxy` は代理人欄です。MVPでは勤務先会社を代理人欄の初期値として扱い、`proxy.name`, `proxy.postal_code`, `proxy.address`, `proxy.phone` は `employer.*` から初期化します。人名として扱う運用に変える場合は、企業マスターまたはケース入力で `proxy.*` を明示的に保存します。

変換例:

| transform | 入力 | 出力 |
|---|---|---|
| `date_yyyymmdd` | `2026-06-01` | `20260601` |
| `date_yyyymm` | `2026-06` | `202606` |
| `boolean_yes_no` | `true` | `有 Yes` |
| `contract_type` | `fixed term contract employee` | `雇用 Employment` |
| `employment_period_type` | `fixed` | `定めあり Fixed` |
| `education_country` | `TRIBHUVAN UNIVERSITY` | `外国 Foreign country` |
| `education_level` | `Bachelor` | `大学 Bachelor` |
| `major_field_university` | `Architectural Engineering` | `工学 Engineer` |
| `sex_ja` | `male` | `男 Male` |
| `marital_yes_no` | `single` | `無 Single` |

## Chrome拡張の責務

Chrome拡張は次だけを担当します。

1. API URL と case_id を受け取る。
2. `/cases/{case_id}/application-data` を呼ぶ。
3. `fillable` と `warnings` を表示する。
4. `rows` を `chrome.storage.local` に保存する。
5. `content.js` に rows を渡す。
6. RASENS DOM に入力する。

Chrome拡張から削るもの:

- `case_data` の解釈
- `rasens_offer_mapping_v2.json` の同梱
- `build_application_data.js` 相当の mapping 解釈
- `visible_when` / `transform` の評価
- RASENSフォーム制約の判断

`content.js` のDOM入力処理は残します。`popup.js` は `/application-data` の取得、`fillable` / `warnings` の表示、入力開始のUI制御だけを担当します。

## mapping を作り直す理由

削除した旧 `rasens_offer_mapping.json` は旧canonical pathと古い物理項目参照が混ざっていました。55件中22件で `field_id` 不在、`field_name` 不在、または `field_id` と `field_name` が別項目を指す疑いがありました。

これは名前の古さだけではなく、値を別の入力欄へ入れるリスクです。そのため、既存mappingを少しずつ修正して延命せず、`rasens_offer_fields.json` の274行フォーム台帳を正として、MVP投入対象の mapping を作り直します。

274行台帳では、自動投入しない行にも扱いを付けます。たとえば `manual`, `settings`, `derived`, `unsupported`, `future` を明示し、「未対応なのか、不要なのか、固定設定で入れるのか」が分かる状態にします。自動投入はMVP対象に絞ります。

`proxy` は代理人として案件データから生成します。MVPでは勤務先会社情報を代理人欄の初期値として扱います。将来、人名の代理人担当者を分ける場合は `proxy.*` を明示保存します。

`intermediary` は取次者です。太田さん側の申請アカウントを持つ申請会社情報を固定設定値として rows 生成時に注入し、Gemini抽出対象にはしません。

## APIの扱い

| API | 扱い |
|---|---|
| `/cases/{case_id}/autofill-data` | 削除済み |
| `/cases/{case_id}/application-data` | Chrome拡張向けの本命API |

旧APIを復活させると、旧Gemini名からautofill名への互換変換が再発するため、canonical v2 方針では使いません。

## エラーと警告

| 状態 | HTTP | body |
|---|---:|---|
| case not found | 404 | `{ "detail": "Case not found" }` |
| case_data missing | 400 | `{ "detail": "case_data not found" }` |
| mapping load failed | 500 | `{ "detail": "mapping load failed" }` |
| not fillable | 200 | `fillable: false`, `warnings: [...]` |

入力不可状態でも 200 を返すのは、Chrome拡張で preview したいケースがあるためです。実投入ボタンは `fillable` を見て制御します。

## 検証

backend側で次をテストします。

- canonical `case_data` から期待rowsが生成される。
- `entry_plan.*`, `applicant.passport.*`, `applicant.immigration_history.*`, `applicant.family.*`, `applicant.education[]`, `applicant.employment_history[]`, `employment.*` の新canonical pathからrowsが生成される。
- `visible_when` が false の項目は出ない。
- 親族明細は `applicant.family.has_japan_relatives_or_cohabitants == true` の場合だけ出る。
- 職歴明細は `applicant.has_employment_history == true` の場合だけ出る。
- 在日親族・同居者と職歴はMVPでは最大3件分の固定index mappingを持つ。
- 日付・boolean・性別・婚姻状態の transform が正しい。
- 職歴の月不詳は `month_unknown` transform で RASENS の「不明な点は無い / 月不詳」ラジオ値に変換する。
- 職歴年月は月不詳が `false` の場合は年月入力、`true` の場合は年のみ入力へ分岐する。
- `field_id` / `field_name` が `rasens_offer_fields.json` と矛盾しない。
- 空値、`unknown`, `not_applicable` は投入されない。

親族生年月日はRASENS上で複数controlを持つ項目です。現行MVPでは通常の年月日テキスト入力を優先し、生年月日の精度radioは実画面QAで追加確認します。
