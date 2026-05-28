# visa-eval

実資料(PDF/Excel)からのAI抽出精度を検証するオフライン評価ワークスペース。

## ディレクトリ構成

```text
visa-eval/
  raw/                 # 元資料 (PDF/Excel/DOCX) — git管理外
  catalog.json         # 資料メタデータ — git管理外
  test_cases_from_raw/     # 単票テストケース — git管理外 (README.mdのみ管理)
    <case_id>/<applicant_id>/
      scenario.json
      input/document_manifest.json
      expected/         # golden: case_data, field_metadata, application_data, review
      generated/        # AI出力先
  blind_runs_from_test_cases/  # ブラインド実行ワークスペース — git管理外
  eval_config/
    suites/            # 評価スイート定義 (git管理)
    prompts/           # ブラインド抽出プロンプト (git管理)
  docs/
```

## 重要ファイル

- `README.md`: 評価ワークスペースの入口、データ機密性ルール
- `docs/単票評価ワークフローまとめ.md`: 単票fixture → Chrome拡張投入までの全体像
- `docs/AIブラインド抽出実行手順.md`: goldenを見せずにAI抽出を実行する手順
- `docs/fixture_contract.md`: fixture入出力とCodex/Gemini評価フローの契約
- `eval_config/suites/single_smoke.json`: 13ケースのスモーク評価スイート
- `eval_config/prompts/blind_single_case_prompt.md`: AI抽出時のプロンプトテンプレート

## PII・gitルール

- **git管理する**: `README.md`, `test_cases_from_raw/README.md`, `eval_config/suites/*.json`, `eval_config/prompts/`, `docs/`
- **git管理しない**: `raw/`, `catalog.json`, `test_cases_from_raw/<case_id>/`, `blind_runs_from_test_cases/`, `**/generated/`
- 実PIIを含むファイルはローカル管理のみ。バグ報告・チャットではPIIを伏せる。

## 評価実行の流れ

1. `visa-eval/scripts/prepare_blind_eval_run.py` でCodex用ブラインド実行ディレクトリを作成
2. Codex/AIエージェントで `blind_runs_from_test_cases/<run_id>/` 内の資料から `case_data.json`, `field_metadata.json`, `review.json` を抽出
3. `visa-eval/scripts/build_application_data.py` で `application_data.json` を決定論的に生成
4. `expected/*.golden.json` と比較して精度を検証

Geminiを評価する場合は、自由操作させず `visa-eval/scripts/run_gemini_bytes_eval.py` で指定ファイルだけをbytesとして backend の scoped Gemini 抽出pipelineへ渡す。GCS/Firestoreは不要。通常フローは次の3コマンド。

```bash
python visa-eval/scripts/run_gemini_bytes_eval.py <fixture_dir> --output-dir <run_output>
python visa-eval/scripts/build_application_data.py <run_output>/case_data.json rasens-autofill/data/mappings/rasens_offer_mapping_v2.json <run_output>/application_data.json
python visa-eval/scripts/compare_with_golden.py --generated <run_output> --expected <fixture_dir>/expected
```

### codex exec によるローカル実行例

```bash
# 1. blind run を作成
python visa-eval/scripts/prepare_blind_eval_run.py \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang

# 2. codex exec で AI 抽出を実行
codex exec \
  -C visa-eval/blind_runs_from_test_cases/<run_id> \
  "$(cat visa-eval/blind_runs_from_test_cases/<run_id>/AGENT_TASK.md)"

# 3. application_data を生成
python visa-eval/scripts/build_application_data.py \
  visa-eval/blind_runs_from_test_cases/<run_id>/generated/case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping_v2.json \
  visa-eval/blind_runs_from_test_cases/<run_id>/generated/application_data.json
```

`<run_id>` は手順1で生成されるディレクトリ名に置き換える。
