# blind_runs_from_test_cases

AIブラインド実行の作業ディレクトリ。`test_cases_from_raw/` から `expected/` を除外したrunディレクトリを作り、AIに正解を見せずに抽出させる。

このディレクトリ配下はすべて git 管理外（restricted test data）。

## ブラインド run の作成

```bash
python3 rasens-autofill/scripts/prepare_blind_eval_run.py \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang
```

タイムスタンプ付きの run ディレクトリが生成される。

## codex exec でのローカル実行

```bash
# 1. blind run を作成
python3 rasens-autofill/scripts/prepare_blind_eval_run.py \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang

# 2. codex exec で AI 抽出を実行
codex exec \
  -C visa-eval/blind_runs_from_test_cases/<run_id> \
  "$(cat visa-eval/blind_runs_from_test_cases/<run_id>/AGENT_TASK.md)"

# 3. application_data を生成
python3 rasens-autofill/scripts/build_application_data.py \
  visa-eval/blind_runs_from_test_cases/<run_id>/generated/case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping.json \
  visa-eval/blind_runs_from_test_cases/<run_id>/generated/application_data.json
```

`<run_id>` は `prepare_blind_eval_run.py` が出力するディレクトリ名（例: `20260512_114953_gijinkoku_a_company_round1__amit_tamang`）に置き換える。

## 実行後のファイル構成

```text
blind_runs_from_test_cases/<run_id>/
  AGENT_TASK.md
  scenario.json
  document_manifest.blind.json
  allowed_reference_paths.txt
  output_contract.md
  documents/            # 元資料へのsymlink
  generated/
    case_data.json      # AI が抽出
    review.json         # AI が抽出
    run_notes.md        # AI が作成
    application_data.json  # build_application_data.py で生成
```

## golden との比較

AI 実行完了後、人間が以下の順で確認する。

1. `generated/run_notes.md` を読む
2. `generated/review.json` を読む
3. `generated/case_data.json` と `expected/case_data.golden.json` を比較
4. `generated/application_data.json` と `expected/application_data.golden.json` を比較

比較は現状手動で行う。`diff` や JSON diff ツールを使う。

```bash
# 例: case_data の差分を見る
diff <(jq -S . visa-eval/blind_runs_from_test_cases/<run_id>/generated/case_data.json) \
     <(jq -S . visa-eval/test_cases_from_raw/<case_id>/<applicant_id>/expected/case_data.golden.json)
```

先に golden を見ると評価者側もミスを見落としやすいため、generated を先に読むこと。
