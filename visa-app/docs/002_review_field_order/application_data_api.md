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
  "workflow_state": "ready_to_fill",
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
| `warnings` | workflowや未確認値に関する警告 |
| `summary` | 生成結果の概要 |
| `rows` | Chrome拡張が入力する行 |

`workflow_state` が `ready_to_fill` でない場合でも、preview目的で `rows` を返してよいです。ただし `fillable` は `false` にし、Chrome拡張側で警告を出します。

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

`required` の意味は分けます。`rows[].required` は `form_definitions` 由来のRASENS入力制約を表し、業務上の不足や人手確認は `review.missing_items`, `review.validation_errors`, `manual_required`, `warnings` で表します。固定設定値で埋まる取次者は、Gemini抽出requiredにはしません。

`intermediary` は取次者で、太田さん側の申請アカウントを持つ申請会社情報を設定から注入します。案件書類やGemini抽出から作る値ではありません。`proxy` は代理人で、受入企業側の担当者を案件データとして扱います。`proxy.address` や `proxy.phone` は `employer.*` から初期化できますが、`proxy.name` は会社名ではなく個人名として確認します。

変換例:

| transform | 入力 | 出力 |
|---|---|---|
| `date_yyyymmdd` | `2026-06-01` | `20260601` |
| `date_yyyymm` | `2026-06` | `202606` |
| `boolean_yes_no` | `true` | `有 Yes` |
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

`proxy` は代理人として案件データから生成します。住所・電話は `employer.*` から初期化候補を作れますが、氏名は会社名ではなく受入企業側の担当者として人確認します。

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
| not ready | 200 | `fillable: false`, `warnings: [...]` |

`ready_to_fill` でなくても 200 を返すのは、Chrome拡張で preview したいケースがあるためです。実投入ボタンは `fillable` を見て制御します。

## 検証

backend側で次をテストします。

- canonical `case_data` から期待rowsが生成される。
- `entry_plan.*`, `applicant.passport.*`, `applicant.immigration_history.*`, `applicant.family.*`, `applicant.education[]`, `applicant.employment_history[]`, `employment.*` の新canonical pathからrowsが生成される。
- `visible_when` が false の項目は出ない。
- 日付・boolean・性別・婚姻状態の transform が正しい。
- `field_id` / `field_name` が `rasens_offer_fields.json` と矛盾しない。
- 空値、`unknown`, `not_applicable` は投入されない。

特に `employer.postal_code` など所属機関まわりの mapping は、フォーム台帳上の `field_id` / `field_name` と一致しているか再確認が必要です。現行mappingには旧フォーム参照が混じっている疑いがあります。
