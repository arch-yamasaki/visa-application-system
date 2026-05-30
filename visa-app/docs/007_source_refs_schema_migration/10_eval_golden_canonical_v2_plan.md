# 10 Eval golden canonical v2 移行計画

## 目的

Gemini の抽出精度を評価する前に、`visa-eval` の golden を現在の canonical v2 に揃える。

MVPでは評価対象を広げすぎない。まず見るのは次の2つだけにする。

```text
1. Gemini が正しい case_data を作れているか
2. その case_data から Chrome拡張用 application_data が正しく作れるか
```

## シンプル版の結論

正本は `expected/case_data.golden.json` だけにする。

```text
expected/
  case_data.golden.json          # 人間確認済みの唯一の正本
  application_data.golden.json   # 旧成果物。初期MVPでは比較に使わない
  review.golden.json             # 残すだけ。初期MVPではgateにしない
```

`application_data` は保存済み golden を読まず、比較時に expected / generated の両方を `case_data` から生成する。

```text
expected/case_data.golden.json ──┐
                                 ├─ backend generator ── application_data比較
generated/case_data.json ────────┘
```

## 触るファイル

| 種別 | ファイル |
|---|---|
| eval script | `visa-eval/scripts/compare_with_golden.py` |
| eval script | `visa-eval/scripts/migrate_golden.py` |
| fixture | `visa-eval/test_cases_from_raw/**/expected/case_data.golden.json` |
| docs | `visa-eval/docs/fixture_contract.md` |
| docs | `visa-eval/test_cases_from_raw/README.md` |
| docs | `visa-app/docs/007_source_refs_schema_migration/11_golden_data_review_workflow.md` |

## 触らないファイル

| ファイル | 理由 |
|---|---|
| `visa-app/backend/application_data.py` | evalでは generator として読むだけ |
| `visa-app/backend/main.py` | Firestore保存やAPIは対象外 |
| `visa-app/frontend/**` | レビューUIとは別タスク |
| `rasens-autofill/extension/**` | Chrome拡張の実入力とは別タスク |

## Cleanup 方針

| 対象 | 方針 | 理由 |
|---|---|---|
| `case_data.golden.json` 内の旧top-level `application` | `entry_plan` / `employment` へ移して削除 | canonical v2 に存在しない |
| top-level `passport` | `applicant.passport` へ移して削除 | 申請人本人の情報 |
| top-level `family` | `applicant.family` へ移して削除 | 申請人本人の情報 |
| top-level `immigration_history` | `applicant.immigration_history` へ移して削除 | 申請人本人の情報 |
| top-level `education` | `applicant.education` へ移して削除 | 申請人本人の情報 |
| top-level `employment_history` | `applicant.employment_history` へ移して削除 | 申請人本人の情報 |
| top-level `qualifications` | `applicant.qualifications` へ移して削除 | 申請人本人の情報 |
| `source_refs` | `case_data.golden.json` から削除 | 値データと証跡を混ぜない |
| `field_metadata` | `case_data.golden.json` から削除 | 初期MVPでは採点しない |
| `supporting_documents` / `raw_intake_pairs` / `golden_status` | 削除 | 抽出値の正解ではない |
| `application_data.golden.json` | 初期MVPでは使わない | 派生物なので比較時生成に寄せる |
| `review.golden.json` | 残すが比較しない | レビュー観点がまだ揺れる |

## Phase 1. 比較対象を絞る

- `compare_with_golden.py` に `--targets` を追加する。
- 初期デフォルトは `case_data,application_data` にする。
- `review` と `field_metadata` は比較しない。
- `application_data` は保存済み `application_data.golden.json` を読まず、expected / generated の `case_data` からその場で生成して比較する。
- レポート冒頭に、値の間違い、抽出漏れ、過剰抽出の件数を出す。

## Phase 2. migration script を1本だけ作る

`visa-eval/scripts/migrate_golden.py` を作る。

役割は次だけ。

```text
expected/case_data.golden.json を canonical v2 に寄せる
旧pathや評価用メタデータを削除する
```

`normalize_case_data.py` や `rebuild_application_golden.py` は作らない。小さいうちは読むファイルを増やさない。

## Phase 3. 1ケースで確認する

対象:

```text
visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang
```

確認すること:

- 旧top-levelが canonical v2 に移っている。
- `source_refs` や `field_metadata` が `case_data.golden.json` に残らない。
- `compare_with_golden.py --targets case_data,application_data` が動く。
- mismatch が旧構造ノイズではなく、値の差分として読める。

## Phase 4. 3ケースで確認する

対象:

```text
visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang
visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/kushang_subba_limbu
visa-eval/test_cases_from_raw/gijinkoku_a_company_round2_family_japan/sanjay_gautam
```

見る観点:

| ケース | 見たいこと |
|---|---|
| `amit_tamang` | 基本ケース |
| `kushang_subba_limbu` | 同じ会社資料で申請人を取り違えないか |
| `sanjay_gautam` | 在日親族・同居者、家族関連 |

受け入れ条件:

- 3件とも旧top-level `application`, `passport`, `family`, `immigration_history`, `education`, `employment_history`, `qualifications` が残らない。
- 3件とも `compare_with_golden.py --targets case_data,application_data` が実行できる。
- `application_data` 比較が `case_data` 由来で再現できる。

## Phase 5以降

Phase 4 が安定してから次を検討する。

- 13件一括移行
- 実 Gemini 出力との比較
- source_ref / bbox の人手レビュー
- `field_metadata` の自動比較
- `review.golden.json` の再設計

## 実行コマンド

project 内の Python を使う。backend generator を読むため、基本は `visa-app/backend/.venv/bin/python` を使う。

`migrate_golden.py` は `--write` を付けない場合 dry-run になる。

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/scripts/migrate_golden.py \
  --write \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang
```

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/scripts/compare_with_golden.py \
  --generated visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/expected \
  --expected visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/expected \
  --targets case_data,application_data
```
