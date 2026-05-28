# レビュー項目・データ契約設計

このディレクトリは、visa-app が扱う申請データの契約と、レビュー画面での表示順を定義するための設計場所です。

## 目的

現在の課題は、同じ意味の情報が次の3つの名前体系に分かれていることです。

| 層 | 役割 | 問題 |
|---|---|---|
| Gemini抽出結果 | 書類から情報を拾うためのAI出力 | Gemini都合の短い/古いフィールド名が残っている |
| Firestore `case_data` | visa-app の案件正本 | 現状はGemini出力に引きずられ、正本として安定していない |
| RASENS / Chrome拡張 | 入管オンライン申請フォームへの投入 | 画面の物理ID・nameと混ざると内部データが壊れやすい |

この設計では、Firestore の `case_data` を唯一の canonical data とし、Gemini raw と RASENS物理フィールドをそこから分離します。

## ドキュメント構成

| ファイル | 役割 |
|---|---|
| [canonical_case_data_v2.md](canonical_case_data_v2.md) | Firestore `CaseDocument v2`、`case_data`、`field_metadata`、`review` の正本設計 |
| [review_field_catalog.md](review_field_catalog.md) | RASENSフォーム全体の順番を基準に、各項目を visa-app でどう扱うかを決める台帳 |
| [application_data_api.md](application_data_api.md) | backend から Chrome拡張へ渡す `application_data` rows API の設計 |
| [canonical_v2_migration_plan.md](canonical_v2_migration_plan.md) | 旧Gemini名互換変換をなくし、Chrome拡張をrows入力だけに薄くする移行計画 |
| [extraction_flow.md](extraction_flow.md) | アップロード後に Gemini 抽出・保存・レビューへ進む現行処理フロー |
| [real_data_extraction_runbook.md](real_data_extraction_runbook.md) | 実データ抽出の成功判定、scope分割、失敗時の切り分け |

## 基本方針

1. Firestore `cases/{case_id}.case_data` は value-only の canonical data にする。
2. OCR/Gemini根拠は `case_data` に埋めず、top-level `field_metadata` に置く。
3. `review` は frontend が扱える object array 形式にする。Geminiの string array は保存前に正規化する。
4. RASENSの `field_id`, `field_name`, `item[187].textData` は `case_data` に入れない。
5. Chrome拡張は backend が返す `application_data.rows` を入力するだけにする。
6. RASENS画面上の番号は `画面番号（参考）` として扱い、技術的なIDや一意キーにはしない。
7. `case_data` の top-level section は増やしすぎない。申請人に属する旅券・履歴・家族・学歴・資格は `applicant.*` に寄せる。
8. 所属機関そのものは `employer.*`、今回の契約・就労条件・活動内容は `employment.*` に分ける。
9. `proxy` は代理人、`intermediary` は取次者として扱う。取次者は太田さん側の申請アカウントを持つ申請会社情報を固定設定値として注入する。
10. RASENS mapping は274行台帳を正とし、MVP対象だけを自動投入する。`transform` と `visible_when` は backend だけが処理する。
11. 旧path互換は作らない。既存Firestoreデータは削除・再抽出で対応する。
12. 実装内部の配列pathは `applicant.education.0.school_name` の dot index 形式に統一する。
13. レビュー画面は Phase 1 では canonical section順、Phase 2 では RASENS順の catalog駆動へ移行する。
14. `case_data.golden` は canonical v2 正解、`application_data.golden` は backend generator の期待出力として分ける。
15. bbox 取得はPDF由来の根拠に対して事前実行する。ただし bbox 失敗は値抽出の失敗扱いにしない。partial extraction はレビュー画面で確認できる形で `extracted` に保存し、全主要scopeが失敗した場合だけ `failed` にする。

## 正本の分担

| データ | 正本 | 備考 |
|---|---|---|
| 案件情報 | Firestore `cases/{case_id}` | アプリの実運用正本 |
| 入力値 | Firestore `case_data` | canonical path / value-only |
| 抽出根拠 | Firestore `field_metadata` | canonical path keyed |
| レビュー結果 | Firestore `review` | 不足・矛盾・人手確認理由 |
| フォーム物理項目 | `rasens-autofill/data/form_definitions/rasens_offer_fields.json` | RASENS画面の台帳 |
| フォーム変換 | `rasens-autofill/data/mappings/rasens_offer_mapping_v2.json` | canonical path -> RASENS field。MVP自動投入対象から開始し、274行台帳へ広げる |
| Chrome投入行 | `/cases/{case_id}/application-data` の `rows` | 派生物。保存正本にしない |
| 評価正解 | `visa-eval/test_cases_from_raw/**/expected/*.golden.json` | restricted test data。`case_data` と `application_data` を別物として比較する |

## canonical section 方針

`case_data` の top-level は次を基本にします。

```text
case
applicant
entry_plan
employer
employment
proxy
intermediary
receiving_method
```

独立top-levelを増やすと、Gemini schema、Firestore、review UI、Chrome拡張mappingのすべてでpathが増えます。そのため、`passport`, `family`, `immigration_history`, `education`, `employment_history`, `qualifications` は原則 `applicant.*` 配下に置きます。

`contract` と `activity_details` は独立sectionにしません。会社そのものではなく今回の就労関係に属するため、`employment.contract_type` と `employment.activity_details` に統一します。

## RASENSフォームとの対応方針

[review_field_catalog.md](review_field_catalog.md) では、RASENSフォームの出現順に沿って、各項目を次の観点で棚卸しします。

| 観点 | 意味 |
|---|---|
| フォーム順 | フォーム台帳内の出現順。表示・検証順に使うが、永続IDではない |
| 画面番号（参考） | RASENS画面に出る番号・見出し。人間向けの目印で、IDではない |
| `canonical path` | Firestore `case_data` の保存先 |
| 入力方針 | Gemini抽出、手入力、固定値、設定値、派生計算、非対応のどれか |
| mapping | Chrome拡張の `application_data` rows へ変換できるか |

## RASENS用語の分離

次の3項目は名前が似ていますが、RASENS上は別項目です。

| RASENS項目 | canonical path | 扱い |
|---|---|---|
| 主たる活動内容 | `entry_plan.main_activity_category` | 申請概要の大分類select。技人国MVPでは固定値候補 |
| 入国目的 | `entry_plan.purpose_of_entry` | 身分事項 No.11 のselect。ユーザー確認画像の項目 |
| 活動内容詳細 | `employment.activity_details` | 所属機関セクション No.11 の600文字textarea。職務内容を文章で説明する |

`主たる活動内容` は `活動内容詳細` ではありません。前者はフォーム全体の分岐に使うカテゴリ、後者は申請人が今回の会社で行う業務説明です。

## 実装への反映順

1. `canonical_case_data_v2.md` を基準に `caseData.ts` と backend schema を更新する。
2. Gemini `schema.py` と `prompt_template.py` を canonical path に寄せる。
3. Firestore保存時に Gemini raw を canonical `case_data` + `field_metadata` + `review` へ正規化する。
4. `review_field_catalog.md` に合わせて `fieldPaths.ts` の section / label / ordering を整理する。
5. `rasens_offer_fields.json` から RASENS全274行の扱い台帳を作り、MVP範囲と非対応範囲を明示する。
6. backend に `/cases/{case_id}/application-data` を追加する。
7. Chrome拡張から mapping と build logic を外し、rows入力だけにする。
8. `visa-eval` の golden とQA手順を canonical v2 / backend generator 前提に更新する。

## 現時点の注意

- 旧実装由来の `applicant.date_of_birth`, `applicant.gender`, `applicant.nationality`, `passport.*`, `application.*`, `family.*`, `immigration_history.*`, `education.*`, `employment_history.*`, `contract.*`, `employment_conditions.*`, `activity_details.description` は canonical v2 の正本では使いません。
- `canonical_case_data_v2.md` は canonical v2 の基本構造契約です。ただし、実務上の条件付き必須やレビュー規則は別途 `review` / completeness rules で扱います。
- 旧 `rasens_offer_mapping.json` は削除済みです。`rasens_offer_mapping_v2.json` を `rasens_offer_fields.json` と照合しながら拡張します。
- `review_field_catalog.md` はMVP主要項目から設計を始めています。RASENS全274行の完全な扱い台帳へ広げる場合は、`rasens_offer_fields.json` を生成元にして更新します。
