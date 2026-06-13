# eval_runs

Gemini bytes eval や比較レポートの実行結果を置くローカル作業ディレクトリ。

このディレクトリ配下は restricted test data として git 管理外にする。実行結果には氏名、住所、旅券番号、雇用条件などが含まれうるため、外部共有しない。

## 役割

`test_cases_from_raw/` は fixture 定義を置く場所です。入力資料、RASENS 出力PDF、golden だけを置き、実行結果は置きません。

`eval_runs/` は実行ごとの出力を置く場所です。Gemini出力、比較レポート、必要な一時派生物を置きます。消しても fixture の正本は失われません。

## 構成

```text
visa-eval/eval_runs/<run_id>/
  report_index.md
  <case_id>/
    case_data.json
    field_metadata.json
    review.json
    comparison_case_data.md
    comparison_case_data.json
    comparison_application_data.md
    comparison_application_data.json
```

## 実行例

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang \
  --run-id gemini_20260603_001

visa-app/backend/.venv/bin/python visa-eval/scripts/compare_with_golden.py \
  --generated visa-eval/eval_runs/gemini_20260603_001/gijinkoku_a_company_round1__amit_tamang \
  --expected visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/expected \
  --targets case_data \
  --output visa-eval/eval_runs/gemini_20260603_001/gijinkoku_a_company_round1__amit_tamang/comparison_case_data.md
```

`--output-dir` を明示した場合はそのパスに出力します。通常は `--run-id` を使い、fixture 配下の `generated/` には出力しません。
