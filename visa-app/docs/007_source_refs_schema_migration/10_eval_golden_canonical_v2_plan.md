# 10 Eval golden canonical v2 移行計画

## 目的

`visa-eval` の golden を、現在の canonical v2 と Gemini raw response 契約に合わせる。

大きな Gemini schema 変更の前に、評価側の正解データと比較スクリプトを整えておく。これにより、後続の PDF bbox 改善、scope 分割、XLSX / DOCX anchor 改善の効果を「古いgoldenとのズレ」ではなく「実際の抽出差分」として見られるようにする。

## 結論

Step 1〜4 は本番アプリに入れない。`visa-eval` の範囲で完結させる。

| Step | 内容 | 書き込み先 | 本番影響 |
|---:|---|---|---|
| 1 | `schema_version` / `case` 補完 | `visa-eval/scripts/` | なし |
| 2 | 旧 `case_data.golden.json` を canonical v2 へ移行 | `visa-eval/test_cases_from_raw/**/expected/` | なし |
| 3 | `field_metadata.golden.json` を分離 | `visa-eval/test_cases_from_raw/**/expected/` | なし |
| 4 | `application_data.golden.json` を再生成 | `visa-eval/test_cases_from_raw/**/expected/` | なし |
| 5 | 1ケースで migrate -> build_application_data -> compare | `generated/` と report | なし |
| 6 | 13件一括移行 | `visa-eval/test_cases_from_raw/**/expected/` | なし |
| 7 | 実 Gemini 出力と新 golden を比較 | `generated/` と report | なし |

本番の `visa-app/backend/application_data.py` は generator として読むだけにする。eval 移行のために本番保存処理や Firestore 構造を変えない。

## 現状整理

| ファイル | 現状 |
|---|---|
| `visa-eval/scripts/run_gemini_bytes_eval.py` | Gemini pipeline をローカルbytesで実行し、`generated/case_data.json`, `field_metadata.json`, `review.json` を出す |
| `visa-eval/scripts/build_application_data.py` | `case_data.json` から backend generator で `application_data.json` を作る |
| `visa-eval/scripts/compare_with_golden.py` | `case_data`, `application_data`, `review` を比較する |
| `visa-eval/test_cases_from_raw/**/expected/case_data.golden.json` | 13件存在。旧pathや評価用メタデータが混ざる可能性がある |
| `visa-eval/test_cases_from_raw/**/expected/application_data.golden.json` | 13件存在。canonical v2 に合わせて再生成が必要 |
| `visa-eval/test_cases_from_raw/**/expected/review.golden.json` | 13件存在。Excel起点 scaffold を含む場合があり、抽出評価の正解としてはまだ揺れる |
| `visa-eval/test_cases_from_raw/**/expected/field_metadata.golden.json` | 現状は存在しない |

## 触るファイル

| 種別 | ファイル |
|---|---|
| eval script | `visa-eval/scripts/normalize_case_data.py` または `visa-eval/scripts/eval_normalize.py` |
| eval script | `visa-eval/scripts/migrate_expected_golden.py` |
| eval script | `visa-eval/scripts/rebuild_application_golden.py` |
| eval script | `visa-eval/scripts/compare_with_golden.py` |
| fixture | `visa-eval/test_cases_from_raw/**/expected/case_data.golden.json` |
| fixture | `visa-eval/test_cases_from_raw/**/expected/field_metadata.golden.json` |
| fixture | `visa-eval/test_cases_from_raw/**/expected/application_data.golden.json` |
| docs | `visa-eval/docs/fixture_contract.md` |
| docs | `visa-eval/test_cases_from_raw/README.md` |
| docs | `visa-app/docs/007_source_refs_schema_migration/06_golden_data_evaluation.md` |

## 触らないファイル

| ファイル | 理由 |
|---|---|
| `visa-app/backend/application_data.py` | eval移行では読むだけ。generatorの仕様変更は別タスク |
| `visa-app/backend/main.py` | Firestore保存やAPIは今回の対象外 |
| `visa-app/frontend/**` | レビューUIの表示順・編集UIとは別タスク |
| `rasens-autofill/data/mappings/rasens_offer_mapping_v2.json` | mapping変更は別タスク |
| `rasens-autofill/extension/**` | Chrome拡張動作は別タスク |

## 方針

### `case_data.golden.json`

value-only の canonical v2 にする。

残す:

- `schema_version`
- `case`
- `applicant.*`
- `entry_plan.*`
- `employer.*`
- `employment.*`
- `education.*`
- `work_history.*`
- `family.*`
- `immigration_history.*`
- `proxy.*`
- `intermediary.*`
- `receiving_method.*`

消す:

- 旧 `application.*`
- 旧 top-level `passport.*`
- 旧 top-level `employment_conditions.*`
- 旧 top-level `source_refs`
- 旧 `field_metadata`
- `golden_status`
- `supporting_documents`
- Gemini 入力に渡していない提出済み申請書PDFだけから分かる値

### `field_metadata.golden.json`

`case_data.golden.json` から分離する。

初期は自動採点しない。人間が「どの資料・ページ・引用から取ったか」を見るための成果物にする。

形式:

```json
{
  "applicant.name_roman": {
    "source_refs": [
      {
        "document_id": "doc_abc123",
        "page": 1,
        "text_quote": "AMIT TAMANG",
        "confidence": 0.95
      }
    ]
  }
}
```

### `application_data.golden.json`

手で作らない。`case_data.golden.json` を backend generator に通して再生成する。

比較対象はまず次に絞る。

- `canonical_path`
- `fill_value`
- `display_value`
- rows の欠落・過剰

`field_id`, `field_name`, `input_type` は後で比較対象に加える。最初から広げすぎると、抽出精度ではなく mapping 表記差分でノイズが増える。

### `review.golden.json`

今回の移行では gate にしない。

理由は、現行 `review.golden.json` に Excel 起点 scaffold や古いレビュー観点が混ざる可能性があるため。まず `case_data` と `application_data` の契約を揃える。`review` は保存された成果物として残し、構造化レビュー設計が固まってから比較対象に戻す。

## 作業計画

### Phase 0. 契約固定

- [ ] `case_data.golden.json` の canonical v2 許可pathを決める。
- [ ] `review.golden.json` は一時的に比較 gate から外す。
- [ ] `field_metadata.golden.json` は人手レビュー用で、自動採点しないことを docs に書く。
- [ ] `schema_version` / `case` は eval normalizer で補完する方針にする。

### Phase 1. eval normalizer を作る

- [ ] `scenario.json` と `input/document_manifest.json` から `schema_version` と `case` を補完する。
- [ ] 旧pathを canonical v2 へ移す。
- [ ] `case_data` 内の `source_refs` / `field_metadata` を分離する。
- [ ] Gemini 入力に渡していない資料由来の値を除外候補として report に出す。
- [ ] まず dry-run で差分だけ出す。

### Phase 2. Amit 1ケースで検証する

- [ ] `gijinkoku_a_company_round1/amit_tamang` を対象にする。
- [ ] `case_data.golden.json` を migrate する。
- [ ] `field_metadata.golden.json` を作る。
- [ ] `application_data.golden.json` を再生成する。
- [ ] `build_application_data.py` を通す。
- [ ] `compare_with_golden.py` を `case_data` / `application_data` 対象で実行する。
- [ ] mismatch が抽出差分なのか、旧golden由来なのかを report に残す。

### Phase 3. 3ケースへ広げる

候補:

| ケース | 見たいこと |
|---|---|
| `gijinkoku_a_company_round1/amit_tamang` | 基本導線 |
| `gijinkoku_a_company_round1/kushang_subba_limbu` | 同じ会社資料で申請人を取り違えないか |
| `gijinkoku_a_company_round2_family_japan/sanjay_gautam` | 在日親族・同居者、家族関連 |

- [ ] 3ケースで migrate を実行する。
- [ ] application_data を再生成する。
- [ ] 比較reportを読み、同じ種類のズレが繰り返していないか見る。

### Phase 4. 13ケース一括移行

- [ ] `eval_config/suites/single_smoke.json` の13ケースを対象にする。
- [ ] migrate を一括実行する。
- [ ] `application_data.golden.json` を一括再生成する。
- [ ] 差分が大きいケースを先に人手レビューする。
- [ ] 変更前後の件数、除外した値、旧path残存数を report に出す。

### Phase 5. 実 Gemini 出力と比較する

- [ ] `run_gemini_bytes_eval.py` で実Gemini出力を作る。
- [ ] generated 側にも同じ normalizer を通す。
- [ ] `case_data` / `application_data` の比較をする。
- [ ] `field_metadata` は document_id / page / text_quote を人手確認する。
- [ ] bbox はこの段階では採点しない。

### Phase 6. 後続改善へ接続する

- [ ] PDF bbox 改善後に `field_metadata` の bbox review を追加する。
- [ ] XLSX cell anchor 後に `sheet_name` / `cell` を追加する。
- [ ] DOCX block anchor 後に `paragraph_index` / `table_index` を追加する。
- [ ] document routing 実装後に、scope別の入力資料と golden の対応を確認する。
- [ ] retry loop 実装後に、missing field だけ再抽出した結果を比較できるようにする。

## 実行コマンド例

project 内の Python を使う。backend 依存を読むため、基本は `visa-app/backend/.venv/bin/python` を使う。

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/scripts/migrate_expected_golden.py \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang \
  --dry-run
```

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/scripts/build_application_data.py \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/expected/case_data.golden.json \
  rasens-autofill/data/mappings/rasens_offer_mapping_v2.json \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/expected/application_data.golden.json
```

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/scripts/compare_with_golden.py \
  --generated visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/generated/<run_id> \
  --expected visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/expected
```

## 受け入れ条件

- 1ケースで migrate -> build_application_data -> compare が通る。
- `case_data.golden.json` に旧pathと証跡情報が残らない。
- `field_metadata.golden.json` が case_data から分離される。
- `application_data.golden.json` が backend generator 由来で再生成される。
- 13ケースで旧path残存数が0になる。
- 本番アプリ、Firestore保存処理、Chrome拡張runtimeに変更を入れない。

## 注意点

旧 golden には「提出済み申請書PDFだけから分かる値」が混ざっている可能性がある。

Gemini 入力に渡していない資料由来の値を golden に残すと、抽出性能ではなく入力条件の問題で missing になる。これは評価として不正確なので、除外するか、別の notes/report に移す。

