# Canonical v2 Migration Plan

- [Canonical v2 Migration Plan](#canonical-v2-migration-plan)
  - [Purpose](#purpose)
  - [Design Principles](#design-principles)
  - [Decisions](#decisions)
  - [MVP Acceptance Criteria](#mvp-acceptance-criteria)
  - [Progress Checklist](#progress-checklist)
  - [Documentation Management](#documentation-management)
  - [Current File Survey](#current-file-survey)
    - [`visa-app/backend/`](#visa-appbackend)
    - [`visa-app/frontend/`](#visa-appfrontend)
    - [`rasens-autofill/`](#rasens-autofill)
    - [`visa-eval/` and Docs](#visa-eval-and-docs)
  - [Agent Roles](#agent-roles)
  - [Implementation Phases](#implementation-phases)
    - [Phase 0: Contract Freeze](#phase-0-contract-freeze)
    - [Phase 1: Gemini Output to Canonical v2](#phase-1-gemini-output-to-canonical-v2)
    - [Phase 2: Firestore and Review UI Cutover](#phase-2-firestore-and-review-ui-cutover)
    - [Phase 3: Backend Application Data Generator](#phase-3-backend-application-data-generator)
    - [Phase 4: Mapping v2 and RASENS Catalog](#phase-4-mapping-v2-and-rasens-catalog)
    - [Phase 5: Chrome Extension Thin Client](#phase-5-chrome-extension-thin-client)
    - [Phase 6: Eval, QA, and Golden Refresh](#phase-6-eval-qa-and-golden-refresh)
    - [Phase 7: Cleanup](#phase-7-cleanup)
  - [Test Plan](#test-plan)
    - [Backend](#backend)
    - [Frontend](#frontend)
    - [Chrome Extension](#chrome-extension)
    - [Eval / QA](#eval--qa)
  - [Risks and Decisions](#risks-and-decisions)
  - [Immediate Next Tasks](#immediate-next-tasks)


## Purpose

旧Gemini名を autofill 用スキーマへ寄せる互換変換を削除し、Firestore `case_data` を canonical v2 に統一する。

消す対象は、同じ意味の値を別名へ移すだけの変換です。

```text
applicant.date_of_birth -> applicant.birth_date
applicant.gender -> applicant.sex
passport.number -> applicant.passport.number
application.has_accompanying -> applicant.family.has_accompanying_members
activity_details.description -> employment.activity_details
```

残す対象は、RASENS画面へ投入するための派生生成です。

```text
canonical case_data
  + form_definitions
  + mapping
  -> application_data.rows
```

## Design Principles

- 旧pathとの二重対応は原則作らない。既存Firestoreデータは削除・再抽出で対応する。
- 防御的プログラミングは、外部入力境界と誤入力リスクが高い箇所だけに限定する。
- 変数名は `case_data`, `field_metadata`, `review`, `form_definitions`, `mapping`, `rows` に揃える。
- `case_data` に RASENS の `field_id`, `field_name`, `item[n].textData` を入れない。
- Chrome拡張に業務判断を置かない。拡張は rows をDOMへ入力し、結果を表示するだけにする。
- 重複実装は削除する。特に mapping / transform / visible_when は backend generator に集約する。
- top-level sectionを増やさない。申請人に属する情報は `applicant.*`、入国計画は `entry_plan.*`、会社属性は `employer.*`、今回の就労関係は `employment.*` に置く。

## Decisions

この移行では、次を決定済みの前提として扱う。

| item | decision |
|---|---|
| `case_data` | Firestore正本は value-only canonical v2。Gemini根拠は `field_metadata`、レビュー判断は `review` に分離する |
| 旧path互換 | 作らない。既存Firestoreデータは削除・再抽出する |
| Gemini schema | 可能な範囲で canonical v2 path に寄せる。短い旧Gemini名を保存前変換する設計にはしない |
| 配列path | 実装内部は `applicant.education.0.school_name` 形式。ドキュメント表示では必要に応じて `applicant.education[0].school_name` も使う |
| enum/select | `case_data` は意味値・内部コードを保存し、RASENSの `value=17` のような画面値は generator で変換する |
| required | schema required、RASENS required、業務レビュー required を分ける |
| RASENS form source | `rasens-autofill/data/form_definitions/rasens_offer_fields.json` をフォーム物理項目の正本にする |
| RASENS mapping | 274行台帳に扱い方を付け、MVP対象だけ自動投入する。現行mappingは延命せず作り直す |
| transform / visible_when | backend generator だけが処理する。Chrome拡張には残さない |
| Chrome拡張 | `/application-data` の `rows` を取得し、RASENS DOMに入力するだけにする |
| `proxy` | 代理人。受入企業側の担当者を案件ごとに確認する |
| `intermediary` | 取次者。太田さん側の申請アカウントを持つ申請会社情報を固定設定値として使う |
| review display | Phase 1は canonical section順。Phase 2で `review_field_catalog` / RASENS順へ寄せる |
| review scope | reviewable項目中心。移行中だけ未分類canonical項目を補助表示する |
| golden split | `case_data.golden` は canonical v2 正解、`application_data.golden` はbackend generator期待出力として分ける |

## MVP Acceptance Criteria

canonical v2移行のMVPは、次をすべて満たした時点で完了とします。

| priority | area | acceptance criteria |
|---|---|---|
| P0 | Data contract | Firestore `cases/{case_id}.case_data` が canonical v2 value-only で保存され、旧Gemini名の `application.*`, top-level `passport.*`, `employment_conditions.*`, `activity_details.description` が通常保存されない |
| P0 | Evidence / review | `field_metadata` と `review.*[].path` が canonical path keyed で揃い、`case_data` にGemini source wrapperやRASENS物理情報が混ざらない |
| P0 | Gemini extraction | `schema.py` と `prompt_template.py` が canonical v2 出力契約を指示し、保存前の旧名互換変換を前提にしない |
| P0 | Backend API | `/cases/{case_id}/application-data` が canonical `case_data`、`form_definitions`、mapping v2、設定値から `rows` を生成する |
| P0 | Backend API | `rows[].required` はRASENS入力制約、業務不足は `review` / `manual_required` / `warnings` で表現される |
| P0 | Proxy / intermediary | `proxy` は代理人として案件データから生成し、`intermediary` は取次者として固定設定値から注入される |
| P0 | Mapping safety | MVP自動投入対象の `field_id` / `field_name` / `input_type` が `rasens_offer_fields.json` と照合され、誤参照疑いが残らない |
| P0 | Chrome extension | Chrome拡張は `/application-data` の `rows` を取得してDOM入力するだけになり、mapping / transform / visible_when を持たない |
| P0 | Review UI | review画面で `applicant.passport.number`, `entry_plan.purpose_of_entry`, `employment.activity_details` をcanonical pathとして確認・編集できる |
| P0 | Tests | backend unit、frontend build、frontend E2E、Chrome拡張のrows投入確認、eval single smoke が通る |
| P1 | RASENS catalog | 274行台帳すべてに `auto_fill`, `manual`, `settings`, `derived`, `unsupported`, `future` などの扱いが付いている |
| P1 | Review order | Phase 1ではcanonical section順、Phase 2では `review_field_catalog.md` / RASENS順で表示できる |
| P1 | Eval refresh | `case_data.golden.json` と `application_data.golden.json` を分離し、backend generator出力を比較できる |
| P2 | Cleanup | 旧API、旧adapter、旧mapping copy、旧テスト、古い説明が削除され、`rg` 確認で意図した移行説明以外に残らない |

MVPで送信自動化はしません。RASENSへの最終送信、確認画面の確定、法的判断の確定は人が行います。

## Progress Checklist

2026-05-25時点のPdMチェックです。実装完了ではなく、要件・設計・コード実態を見た進捗です。

### Completed

- [x] canonical v2 のtop-level section方針を文書化した。
- [x] `passport` は `applicant.passport.*`、契約・給与・活動内容は `employment.*` に寄せる方針を文書化した。
- [x] `proxy` は代理人、`intermediary` は取次者固定設定値として分ける方針を文書化した。
- [x] `/application-data` は backend が rows を生成し、Chrome拡張は rows 入力だけにする責務分離を文書化した。
- [x] RASENS画面番号はIDではなく人間向け参考情報として扱う方針を文書化した。
- [x] eval の `case_data.golden` と `application_data.golden` を分ける方針を文書化した。

### Progress

- [x] `case_data.schema.json` と `frontend/src/types/caseData.ts` を canonical v2 に更新する。
- [x] `backend/extractors/schema.py` と `prompt_template.py` を canonical v2 に更新する。
- [x] Gemini raw `{value, source}` を `case_data` value-only と `field_metadata` に分離して保存する。
- [x] `backend/autofill_adapter.py` に依存しない `application_data` generator の最小実装とunit testを追加する。
- [x] `/cases/{case_id}/application-data` endpoint を追加する。
- [x] mapping v2 を `rasens_offer_fields.json` 正本で再作成する。
- [x] Chrome拡張から `build_application_data.js` と同梱mappingを削除する。
- [x] review UI の旧path label / section fallback を削除する。
- [x] `visa-eval` のgolden生成スクリプトと比較手順を canonical v2 / backend generator 前提に更新する。
- [x] 実PIIを使わず、demo mode で Playwright E2E を実施する。
- [ ] 実案件データを使う手動QAは、restricted data としてローカルで別途実施する。
- [x] 旧API `/autofill-data`、`autofill_adapter.py`、旧互換テスト、旧demo生成物を削除する。

## Documentation Management

実装中は、コード変更と同じPRまたは同じ作業単位で次のdocsを更新します。

| doc | update trigger |
|---|---|
| `canonical_case_data_v2.md` | canonical path、top-level section、型、required方針を変えた時 |
| `review_field_catalog.md` | RASENS項目の扱い、MVP対象、入力方針、mapping有無を変えた時 |
| `application_data_api.md` | `/application-data` response、row schema、`fillable`、warnings、generator責務を変えた時 |
| `canonical_v2_migration_plan.md` | Phase完了、受け入れ条件、リスク、削除対象が変わった時 |
| `rasens-autofill/docs/データ設計.md` | Chrome拡張・mapping・form_definitionsの責務が変わった時 |
| `rasens-autofill/docs/フォーム項目一覧.md` | RASENSフォーム台帳や274行分類を更新した時 |
| `visa-app/QA_MANUAL.md` | QA手順、確認ポイント、E2E実行方法が変わった時 |
| `visa-eval/README.md` / `visa-eval/docs/*` | eval fixture構成、golden生成、比較手順が変わった時 |

Phase完了の印は、この計画書の checklist に付けます。コードだけ完了してdocsが未更新の場合、そのPhaseは未完了として扱います。

## Current File Survey

### `visa-app/backend/`

| path | 現状 | 移行方針 |
|---|---|---|
| `main.py` | FastAPI、Firestore保存、`/cases/{case_id}/autofill-data` | canonical保存、`/application-data`追加、旧endpoint削除 |
| `autofill_adapter.py` | 旧Gemini名 -> autofill名の互換変換 | 最終削除 |
| `extractors/schema.py` | Gemini response schema。旧pathが多い | scoped schemaをcanonical v2へ更新 |
| `extractors/prompt_template.py` | `employment_conditions` 等の旧キー名を正規として指示 | canonical v2の出力契約へ更新 |
| `extractors/gemini.py` | FieldValue処理、`display_case_data`生成、旧employment alias正規化 | `case_data` value-only + `field_metadata`生成へ整理 |
| `extractors/bbox_locator.py` | bbox対象pathが旧path | canonical pathへ更新 |
| `tests/test_autofill_adapter.py` | 削除対象の互換変換を固定するテスト | `autofill_adapter.py`削除時に削除 |
| `tests/test_gemini.py` | Gemini正規化・prompt・extractのテスト | canonical path前提へ更新 |

### `visa-app/frontend/`

| path | 現状 | 移行方針 |
|---|---|---|
| `src/types/caseData.ts` | `application`, top-level `passport`, `family`, `employment_conditions` など旧構造 | canonical v2型へ更新 |
| `src/lib/fieldPaths.ts` | section/label辞書に旧pathとfallbackが多い | canonical-onlyに整理 |
| `src/api/mockData.ts` | demo data と `field_metadata` が旧path | canonical v2 fixtureへ更新 |
| `src/components/review/*` | `flattenCaseData()` ベースで比較的汎用 | 配列path編集とraw値編集だけ注意 |
| `src/pages/ReviewPage.tsx` | dot path更新処理が配列に弱い | `applicant.education.0.*` を壊さない更新処理へ |
| `frontend/e2e/review-flow.spec.ts` | 具体path依存は少ない | canonical section順と主要reviewable項目の表示確認を追加 |

### `rasens-autofill/`

| path | 現状 | 移行方針 |
|---|---|---|
| `data/form_definitions/rasens_offer_fields.json` | RASENSフォーム274行 / 335 controlsの台帳 | フォーム物理項目の正本として維持 |
| `data/mappings/rasens_offer_mapping.json` | 主要55件の旧mapping。物理項目不一致疑いあり | canonical v2で作り直し |
| `data/schemas/case_data.schema.json` | 旧autofill寄りschema | canonical v2 schemaへ置換または visa-app 側へ移動 |
| `scripts/build_application_data.py` | case_data + mapping -> rows のCLI | backend generatorへ移す。評価用CLIはbackend共通ロジックを呼ぶ形に変更 |
| `extension/build_application_data.js` | 拡張内で `value_path`, `transform`, `visible_when` を評価 | 削除 |
| `extension/popup.js` | `/autofill-data`取得、同梱mapping読込、rows生成 | `/application-data`取得へ変更 |
| `extension/content.js` | rowsをDOMへ入力 | 残す。責務は理想形に近い |
| `extension/rasens_offer_mapping.json` | 拡張同梱mapping | 削除 |

### `visa-eval/` and Docs

| path | 現状 | 移行方針 |
|---|---|---|
| `visa-eval/README.md` | `build_application_data.py` 前提 | backend generator前提へ更新 |
| `visa-eval/docs/*` | 単票評価と投入生成が旧path・旧script前提を含む | canonical v2評価手順へ更新 |
| `visa-eval/eval_config/prompts/blind_single_case_prompt.md` | `application.activity_details` 等が残る | `employment.activity_details` へ更新 |
| `visa-app/QA_MANUAL.md` | `employment_conditions` が残る | `employment` へ更新 |
| `rasens-autofill/docs/*` | Chrome拡張寄り説明と旧生成手順が混在 | 実装補助資料にし、正本はこのディレクトリへ寄せる |

## Agent Roles

開発時は、次の5役割でレビューと実装を分担します。

| role | responsibility | done signal |
|---|---|---|
| PdM | 要件、優先順位、受け入れ条件、docs更新を管理する | checklist と acceptance criteria が更新され、未完了リスクが見える |
| UI/UX Designer | review UI、Chrome拡張popup、画面状態、アクセシビリティを確認する | ユーザーが確認すべき項目、警告、入力不可状態が迷わず分かる |
| Lead Engineer / Architect | 設計方針、影響範囲、削除方針、テスト戦略を決める | 旧互換を残す箇所と削る箇所が明確で、重複実装が増えない |
| Engineer | 既存規約に沿って小さく実装し、不要コードを削除する | 各Phaseの実装とunit/buildが通る |
| QA | E2E、Chrome DevTools、実資料eval、PII管理観点で検証する | 受け入れ条件に沿った結果と残リスクが記録される |

実装workstreamは次のように分けます。5役割のうち、Lead Engineerが設計レビュー、Engineerが実装、QAが検証、PdMが完了判定を担当します。

| role | owner scope | main deliverables |
|---|---|---|
| Data Contract Agent | `canonical_case_data_v2.md`, `case_data.schema.json`, `caseData.ts` | canonical v2 path / type / required方針の確定 |
| Backend Extraction Agent | `schema.py`, `prompt_template.py`, `gemini.py`, `bbox_locator.py` | Gemini出力をcanonical v2へ寄せ、`field_metadata`をcanonical path keyedにする |
| Backend API Agent | `main.py`, new generator module, backend tests | `/application-data`、Firestore保存契約、旧`/autofill-data`削除 |
| Frontend Review Agent | `caseData.ts`, `fieldPaths.ts`, review UI, mockData | canonical v2表示、旧pathラベル削除、配列path編集対応 |
| RASENS Mapping Agent | `rasens_offer_fields.json`, mapping v2, transform rules | 274行台帳からMVP mappingを再作成し、form_definitions照合を実装 |
| Chrome Extension Agent | `extension/api_client.js`, `popup.js`, `content.js`, manifest assets | rows取得・DOM入力だけの薄い拡張へ整理 |
| Eval / QA Agent | `visa-eval`, QA docs, golden fixtures | canonical v2 golden、評価手順、QA手順を更新 |
| Cleanup Agent | stale files, old tests, duplicate docs | `autofill_adapter.py`, old mapping copies, old tests,古い説明の削除 |

## Implementation Phases

### Phase 0: Contract Freeze

目的: 実装前に canonical path と保存境界を固定する。

Tasks:

- `canonical_case_data_v2.md` を正本として、MVP対象pathを確定する。
- `entry_plan.main_activity_category`, `entry_plan.purpose_of_entry`, `employment.activity_details` の違いを固定する。
- `field_metadata`, `review`, `document_manifest` は `case_data` 外の top-level として固定する。
- `case_data` は value-only とし、Gemini raw の `{value, source}` は保存前に分離する。
- required は schema required、RASENS required、業務レビュー required に分離する。
- dot path表記を実装では `applicant.education.0.school_name`、ドキュメント表示では必要に応じて `applicant.education[0].school_name` とする。
- `proxy` は代理人、`intermediary` は取次者固定設定値として固定する。
- enum/selectは canonical 側にRASENS物理valueを保存せず、backend generatorでRASENS valueへ変換する。

Done:

- 新旧path対応表が `canonical_case_data_v2.md` に揃っている。
- 旧pathを延命する方針が残っていない。
- `proxy` と `intermediary` の値の出所が文書上で分かれている。
- 採用済み決定がこの計画書に明記されている。

### Phase 8: Real Data Extraction Hardening

目的: 実データ抽出が遅い、途中で止まる、または一部scopeだけ成功する問題を潰し、Chrome拡張へ渡せる品質ゲートを明確にする。

Tasks:

- 実データ抽出と bbox 取得の成功判定を分離する。
- scope単位の成功/失敗をログと保存状態から追えるようにする。
- partial extraction は人間レビュー可能にする。全主要scopeが失敗した場合だけ `failed` にする。
- scopeごとに渡す文書と prompt 上の書類一覧を一致させる。
- ファイル名推測から `document_role` / 自動分類結果ベースの文書ルーティングへ移行する。
- ローカル実データQAの手順を [real_data_extraction_runbook.md](real_data_extraction_runbook.md) に集約する。
- `/application-data` の `fillable` 条件は workflow 状態ベースにする。必須不足や一部未入力は投入を止めず、人間レビューで補完する。

Done:

- `/extract-stream` が中断されても `workflow_state=extracting` に残らない。
- 一部scope失敗時も成功scopeの結果をレビュー可能にし、失敗scopeを `review.validation_errors` に残す。
- `extracted` 相当のケースでは `/application-data.fillable=true` になる。

### Phase 1: Gemini Output to Canonical v2

目的: Geminiが最初から canonical v2 に近い形で出力し、`autofill_adapter.py` が不要になる土台を作る。

Tasks:

- `schema.py` の scoped schema を更新する。
  - S1: `applicant`, `applicant.passport`, `entry_plan`, `applicant.immigration_history`, `applicant.family`
  - S2: `employer`, `employment`
  - S3: `applicant.education[]`, `applicant.qualifications`
  - S6: `review`
- `prompt_template.py` の旧キー名指示を削除する。
- `gemini.py` で Gemini raw `{value, source}` を `case_data` value-only と `field_metadata` に分離する。
- `display_case_data` を削除候補にし、保存契約は `case_data` に統一する。
- `bbox_locator.py` の対象pathをcanonicalへ更新する。

Done:

- Gemini抽出結果の保存済み `case_data` に `application`, top-level `passport`, `employment_conditions`, `activity_details.description` が出ない。
- `field_metadata` key が canonical path と一致する。

Concerns:

- Gemini response schema の state数制限。scope分割は維持する。
- 配列項目は最初から広げすぎない。MVPでは最終学歴1件、職歴は必要範囲から始める。

### Phase 2: Firestore and Review UI Cutover

目的: visa-app UI が canonical v2 だけを読む状態にする。

Tasks:

- `main.py` の新規case skeletonを canonical v2 へ更新する。
- `main.py` の抽出保存を `result.case_data`, `result.field_metadata`, `result.review` に整理する。
- `frontend/src/types/caseData.ts` を canonical v2 に更新する。
- `frontend/src/lib/fieldPaths.ts` から旧pathラベルを削除する。
- `getSectionForPath()` は top-level だけでなく prefix で判断する。
  - `applicant.education.*` -> 申請人に関する情報等
  - `applicant.employment_history.*` -> 申請人に関する情報等
  - `applicant.qualifications.*` -> 申請人に関する情報等
  - `employment.*` -> 所属機関に関する情報等
- `mockData.ts` と `field_metadata` fixtureを canonical v2 に更新する。
- `ReviewPage` の field update が配列pathを壊さないようにする。
- `FieldRow` の編集初期値は表示値ではなくraw値にする。
- Phase 1のレビュー表示は canonical section順にする。
- 表示対象は reviewable 項目中心にし、移行中だけ未分類canonical項目を補助表示する。

Done:

- review画面で `applicant.passport.number`, `entry_plan.purpose_of_entry`, `employment.activity_details` が表示される。
- 旧pathラベルが表示用辞書に残っていない。
- `field_metadata` と `review.missing_items[].path` は dot index の canonical path で照合できる。
- frontend build と主要E2Eが通る。

### Phase 3: Backend Application Data Generator

目的: Chrome拡張から mapping / transform / visible_when を取り除く。

Tasks:

- backendに generator module を追加する。
  - input: `case_data`, `form_definitions`, `mapping`
  - output: `application_data.rows`
- `/cases/{case_id}/application-data` を追加する。
- `rasens_offer_fields.json` を読んで mapping の `field_id`, `field_name`, `input_type` を照合する。
- transform は必要最小限にする。
  - `date_yyyymmdd`
  - `date_yyyymm`
  - boolean yes/no
  - select/radio label/value mapping
- `draft`、`extracting`、`failed` は preview可能だが `fillable: false` を返す。
- `intermediary` は太田さん側の申請アカウントを持つ申請会社情報から注入する固定設定値として扱う。
- `proxy` は代理人として案件データに持つ。住所・電話は `employer.*` から初期化できるが、氏名は会社名ではなく受入企業側の担当者として人確認する。

Done:

- canonical `case_data` から rows が生成される。
- mapping不一致は投入前に検出される。
- `entry_plan.main_activity_category` と `entry_plan.purpose_of_entry` が別rowとして生成される。
- `employment.activity_details` は textarea row として生成される。

### Phase 4: Mapping v2 and RASENS Catalog

目的: 旧mapping延命ではなく、フォーム台帳を正としてMVP mappingを作り直す。

Tasks:

- `rasens_offer_fields.json` から274行のベース台帳を生成・確認する。
- 274行すべてに `auto_fill`, `manual`, `settings`, `derived`, `unsupported`, `future` などの扱いを付ける。
- `review_field_catalog.md` のMVP対象行に canonical path / 入力方針 / mapping有無を埋める。
- mapping v2 は `field_id` と `field_name` の両方を `form_definitions` と照合できる形にする。
- 旧 `application.*`, top-level `passport.*`, top-level `family.*`, top-level `immigration_history.*` を mapping から削除する。
- mapping はbackendが読む設計資産とし、Chrome拡張へ同梱しない。

Done:

- MVP mappingに旧canonical pathが残っていない。
- MVP以外の行も、未対応なのか、手入力なのか、設定値なのかが台帳上で分かる。
- 所属機関まわりの `field_id` / `field_name` 不一致疑いが解消されている。

### Phase 5: Chrome Extension Thin Client

目的: Chrome拡張を rows 入力だけにする。

Tasks:

- `api_client.js` を `/cases/{case_id}/application-data` へ変更する。
- `popup.js` から mapping読込と `buildApplicationData.buildRows()` 呼び出しを削除する。
- `build_application_data.js` と `extension/rasens_offer_mapping.json` を削除する。
- `content.js` は rows DOM入力責務を維持する。
- previewでは backend が返す `warnings`, `fillable`, `rows` を表示する。

Done:

- Chrome拡張に `case_data` 解釈が残っていない。
- 拡張同梱mappingがない。
- rows fixtureでDOM入力確認ができる。

### Phase 6: Eval, QA, and Golden Refresh

目的: 実資料評価とQA手順を canonical v2 に揃える。

Tasks:

- `visa-eval` の prompt と docs を canonical v2 へ更新する。
- `case_data.golden.json` を canonical v2 で再作成する。
- `application_data.golden.json` は backend generator の期待出力として扱う。
- `review.golden.json` は不足・矛盾・人確認理由の期待値として扱い、フォーム投入結果とは分ける。
- `build_application_data.py` は backend generator を呼ぶCLIに変えるか削除する。
- `QA_MANUAL.md` の `employment_conditions` など旧説明を更新する。
- 実PIIの `generated/` や `expected/` はgit管理外のまま扱う。

Done:

- single smokeの対象ケースで canonical v2 `case_data`, `review`, `application_data` を比較できる。
- QA手順に `/application-data` と Chrome拡張薄化後の確認項目がある。

### Phase 7: Cleanup

目的: 古い変換と重複実装を削除する。

Tasks:

- `visa-app/backend/autofill_adapter.py` を削除する。
- `visa-app/backend/tests/test_autofill_adapter.py` を削除する。
- `main.py` の `/cases/{case_id}/autofill-data` を削除する。
- `Dockerfile` の `COPY backend/autofill_adapter.py .` を削除する。
- `gemini.py` の `_normalize_employment_keys()` など旧別名互換を削除する。
- 旧schema / 旧generated demo / 旧mapping copy を削除またはcanonical v2で再生成する。

Done:

- `rg "autofill_adapter|/autofill-data|employment_conditions|application.activity_details|passport\\.number"` で、意図した旧説明以外が残らない。
- backend / frontend / extension の主要テストが通る。

## Test Plan

### Backend

- `test_gemini.py`
  - scoped extraction schema が canonical v2 path を返す。
  - `{value, source}` から value-only `case_data` と `field_metadata` が生成される。
  - `field_metadata` key が canonical path になる。
- new `test_application_data.py`
  - canonical pathから rows が生成される。
  - `field_id` / `field_name` が `form_definitions` と一致しないmappingは失敗する。
  - `entry_plan.planned_entry_date` が `YYYYMMDD` に変換される。
  - `entry_plan.main_activity_category`, `entry_plan.purpose_of_entry`, `employment.activity_details` が別rowになる。

### Frontend

- `npm run build`
- review画面で以下が表示される。
  - `entry_plan.purpose_of_entry`
  - `applicant.passport.number`
  - `employment.activity_details`
- 配列pathの編集で `applicant.education` がobject化しない。

### Chrome Extension

- rows fixtureを読み、`content.js` がtext/select/radio/textareaを入力できる。
- popupは `/application-data` の `fillable` と `warnings` を表示する。
- 拡張内に mapping / transform / visible_when の実装が残らない。

### Eval / QA

- `visa-eval` の single smoke で canonical `case_data`, `review`, `application_data` を比較する。
- 実PIIはgit管理外を維持する。
- RASENSで最終送信はしない。

## Risks and Decisions

| item | decision |
|---|---|
| Existing Firestore data | 本番前なので削除・再抽出。migration APIは作らない |
| Old path compatibility | 作らない。外部入力境界の検出ログを除き、旧path fallbackは実装しない |
| Gemini state limit | scope分割を維持し、MVP対象に絞る |
| Schema location | Firestore正本schemaは visa-app 側へ寄せるのが自然。RASENS入力制約は rasens-autofill 側に残す |
| RASENS physical IDs | `case_data` には入れず、generator / mapping 層だけで扱う |
| Proxy / intermediary | `proxy` は代理人として案件ごとに人確認、`intermediary` は取次者として太田さん側の申請アカウントを持つ申請会社情報の固定設定値 |
| Review order | Phase 1は canonical section順。Phase 2でRASENS順カタログ駆動へ移行 |
| Review scope | reviewable項目中心。移行中だけ未分類canonical項目を補助表示 |
| Golden split | `case_data.golden` と `application_data.golden` を分け、後者はbackend generator出力で固定する |

## Immediate Next Tasks

1. Data Contract Agentが `canonical_case_data_v2.md` と `caseData.ts` の差分を埋める。
2. Backend Extraction Agentが `schema.py` scoped schema をcanonical v2へ更新する。
3. Backend API Agentが `/application-data` generator の最小実装を設計する。
4. RASENS Mapping Agentが MVP mapping v2 の対象行を `review_field_catalog.md` から確定する。
5. Frontend Review Agentが `fieldPaths.ts` をcanonical-onlyへ整理する。
