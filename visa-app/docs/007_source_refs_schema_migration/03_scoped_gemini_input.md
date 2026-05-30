# 03 scope 別 Gemini 入力

Status: 実装済み

## 目的

Gemini抽出を現在より細かい scope に分け、schema / prompt / merge の責務を明確にする。

document routing はこの段階では本格実装しない。まずは scope 分割を安定させる。

## 実装前の調査対象ファイル

| ファイル | 現状 |
|---|---|
| `backend/extractors/schema.py` | `SCOPE_SCHEMAS` は `S1`, `S2`, `S3`, `S6` の4つ |
| `backend/extractors/prompt_template.py` | `identity`, `employer`, `education`, `review` の4 scope prompt |
| `backend/extractors/gemini.py` | `extract_all_scopes()` が `identity`, `employer`, `education` を並列実行し、最後に `review` |
| `backend/extractors/gemini_pipeline.py` | 各scopeに同じ `build_gemini_contents(prepared)` を渡している |
| `backend/extractors/document_preprocessor.py` | 拡張子別に `PreparedDocuments` へ振り分けるだけ |
| `backend/extractors/document_models.py` | `PreparedDocuments` は全書類の束で、scope別indexを持たない |

## 実装前の問題

scope schema / prompt は存在するが、入力書類は scope ごとに分かれていない。

```python
contents_by_scope = {
    "identity": build_gemini_contents(prepared),
    "employer": build_gemini_contents(prepared),
    "education": build_gemini_contents(prepared),
    "review": build_gemini_contents(prepared),
}
```

つまり、現状は「scopeごとに聞く内容は違うが、見せる書類は同じ」状態。

これは routing 実装前としては許容できるが、scopeを増やすなら次の整理が必要。

- scope名とschema名の対応を分かりやすくする
- scopeごとの owner field を重複させない
- merge時に同じ path を複数scopeが書かないようにする
- review scope に渡す context は value-only にする
- 将来 document routing を差し込める境界を残す

## 新しいscope案

| scope | owner field | 主な対象 |
|---|---|---|
| `applicant_identity` | `applicant.*`, `applicant.passport.*`, `applicant.japan_contact.*` | 氏名、生年月日、国籍、性別、旅券、住所 |
| `entry_plan` | `entry_plan.*`, `applicant.family.*` | 入国目的、在留予定期間、上陸予定港、査証申請予定地、同伴者、在日親族 |
| `immigration_history` | `applicant.immigration_history.*` | 過去の入出国歴、COE申請歴、退去強制、犯罪歴 |
| `education` | `applicant.education[]`, `applicant.qualifications.*` | 最終学歴、学校名、卒業年月、専攻、資格 |
| `employment_history` | `applicant.has_employment_history`, `applicant.employment_history[]` | 職歴の有無、職歴明細 |
| `employer` | `employer.*` | 所属機関名、住所、法人番号、業種、売上、従業員数 |
| `employment` | `employment.*` | 契約形態、就労開始日、就労予定期間、給与、役職、職務内容 |
| `proxy_intermediary` | `proxy.*`, `intermediary.*` | 代理人、取次者。初期は固定値/別処理中心のため抽出対象に入れるか要判断 |
| `review` | `review` | 不足・矛盾・人判断が必要な論点 |

`proxy_intermediary` は今回の実装では未採用。代理人・取次者は固定値や会社情報由来の生成と混ざりやすいため、Gemini抽出scopeにはまだ入れない。

## scope分割の判断

### 分けるべきもの

- `entry_plan` と `applicant_identity`
  - 入国目的、予定港、期間は申請設計寄りで、氏名・旅券とは性質が違う。
- `immigration_history`
  - 無・有の推測やデフォルト方針が多く、本人基本情報と混ぜるとpromptが重い。
- `employer` と `employment`
  - 会社情報と契約条件は参照書類が重なっても、canonical pathのownerが違う。
- `education` と `employment_history`
  - RASENS上は近いが、配列構造と判断基準が違う。

### 分けすぎないもの

- `passport` は `applicant_identity` に含める。
- `japan_contact` も `applicant_identity` に含める。
- `family` は入国計画との関連が強いため `entry_plan` 側で扱う。
- `proxy_intermediary` は、今すぐGemini抽出に入れず、固定値/会社情報からの生成として別管理でもよい。

## schema.py 作業計画

1. 現行 `SCOPE1_IDENTITY_SCHEMA` を `applicant_identity`, `entry_plan`, `immigration_history` に分割する。
2. 現行 `SCOPE2_EMPLOYER_SCHEMA` を `employer`, `employment` に分割する。
3. 現行 `SCOPE3_EDUCATION_SCHEMA` を `education`, `employment_history` に分割する。
4. `SCOPE_SCHEMAS` の key を `S1` 形式から、実装上分かりやすい scope名寄りへ変えるか検討する。
5. 各 scope schema は owner field だけを返す。
6. 配列は最大3件方針を prompt 側で明示し、schema側は配列を許容する。

## prompt_template.py 作業計画

1. `_SCOPE_INSTRUCTIONS` を新scope名に合わせる。
2. `_SCOPED_COMMON_RULES` は共通のまま維持する。
3. scope固有のデフォルト方針を該当scopeだけに置く。
   - 例: 滞在予定期間は `entry_plan`
   - 例: 犯罪歴/COE歴は `immigration_history`
   - 例: 就労予定期間は `employment`
4. `SCOPE_DOCUMENT_ROLES` は当面すべて `None` のまま維持する。
5. routing前提の説明を prompt に入れすぎない。

## gemini.py 作業計画

1. `_SCOPE_KEY_MAP` を新scopeに合わせる。
2. `extraction_scopes` を新scope一覧にする。
3. `ThreadPoolExecutor(max_workers=3)` は scope増加後に調整する。
   - 初期案: `max_workers=4`
   - 全scope同時実行はAPI負荷とrate limitを見て判断
4. `_deep_merge_case_data()` はそのまま使えるが、同一path競合がない前提にする。
5. conflict detection は初期では入れない。owner field分離で避ける。
6. review scope には `merged_case_data` を渡す。

## gemini_pipeline.py 作業計画

1. 初期は全scopeに同じ `PreparedDocuments` から作った contents を渡す。
2. `contents_by_scope` と `documents_by_scope` を作る責務は維持する。
3. 将来 routing のために、`build_gemini_contents(prepared)` を scope引数付きにできる形へ分ける。
4. `scope_input_built` log は維持し、scope増加後も parts/documents を追えるようにする。
5. bbox attach は scope分割後も抽出後に一度だけ行う。

## document_preprocessor.py / document_models.py 作業計画

scope分割だけの段階では大きく変えない。

ただし将来 routing のため、次の設計だけ決めておく。

- `LoadedDocument` は upload manifest 由来の `document_role` を保持する。
- `PreparedDocuments` は将来 `documents_by_id` を持てるようにする。
- PDF / text / image の各 list だけでなく、document単位で content type を引ける index が必要。

初期実装では、routing用 index の追加はまだ行わない。

## document routing との境界

scope分割後も、document routing は後工程。

| 段階 | やること | やらないこと |
|---|---|---|
| scope分割 | schema/prompt/mergeの責務を分ける | 書類をscope別に絞る |
| routing準備 | `contents_by_scope` の境界を維持する | 強い分類で書類を落とす |
| routing実装 | scopeごとに manifest と contents を揃える | review scope まで絞りすぎる |

## 受け入れ条件

- 各 canonical path の owner scope が一意に決まっている。
- 全scopeが成功したとき、既存レビューUIに必要な `case_data`, `field_metadata`, `review` が保存される。
- 一部scopeが失敗しても、成功scopeの結果は保存され、`review.validation_errors` に失敗scopeが残る。
- `scope_input_built` と `gemini_metric` で scope別の処理状況を追える。
- document routing を入れなくても動く。

## リスク

- scopeを増やすとGemini呼び出し回数が増える。
- 並列数を上げすぎるとrate limitやtimeoutの原因になる。
- schemaを細かくしすぎると、scope間の整合性をreviewに頼る割合が増える。
- `proxy_intermediary` は固定値・会社情報生成・Gemini抽出のどれが正かを別途決める必要がある。

## 推奨順

1. owner scope表を確定する。
2. `schema.py` を新scopeに分ける。
3. `prompt_template.py` を新scopeに分ける。
4. `gemini.py` の `_SCOPE_KEY_MAP` と `extraction_scopes` を更新する。
5. `gemini_pipeline.py` のログと contents_by_scope を新scope対応にする。
6. 実データ1件で、scope別に root が欠けないか確認する。

## 実装内容

- `backend/extractors/schema.py`
  - 新scope schemaを追加
  - 旧 `S1/S2/S3/S6` alias は互換として維持
- `backend/extractors/prompt_template.py`
  - `_SCOPE_INSTRUCTIONS` を新scope名に分割
  - `SCOPE_DOCUMENT_ROLES` は全scope `None` のまま維持
- `backend/extractors/gemini.py`
  - `_SCOPE_KEY_MAP` を新scope名へ変更
  - `EXTRACTION_SCOPES` を追加
  - 並列数は `min(4, len(EXTRACTION_SCOPES))`
  - review scope には value-only に正規化した merged case_data を渡す
- `backend/extractors/gemini_pipeline.py`
  - `contents_by_scope` / `documents_by_scope` を `EXTRACTION_SCOPES + review` から生成
  - document routing は未実装。全scopeに全書類を渡す方針を維持
- `backend/tests/test_gemini.py`
  - 新scope一覧が実行されることを確認
  - 一部scope失敗時の reviewable result を新scope名に更新

## 確認結果

2026-05-31 に実データ1件で確認済み。

- `visa-app/backend` で `.venv/bin/python -m pytest -q` を実行し、108件すべて通過。
- 実データ抽出は約45.8秒で完了。
- `applicant_identity`, `entry_plan`, `immigration_history`, `education`, `employment_history`, `employer`, `employment`, `review` が成功。
- failed scopes は0件。
- local frontend の案件一覧・レビュー画面で抽出結果を確認。
- `visa-app/frontend` で `npm run build` が通過。
- 詳細: [QA_REAL_DATA_2026-05-31.md](QA_REAL_DATA_2026-05-31.md)

## 残課題

- Cloud Run上でのtimeoutやrate limitを確認する
- document routing は07で実装する
- Chrome拡張の取次者入力バグ修正は別タスクで扱う
