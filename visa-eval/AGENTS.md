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
      expected/         # golden: case_data, application_data, review
      generated/        # AI出力先
  blind_runs_from_test_cases/  # ブラインド実行ワークスペース — git管理外
  eval_config/
    suites/            # 評価スイート定義 (git管理)
    prompts/           # ブラインド抽出プロンプト (git管理)
  docs/
```

## 重要ファイル

- `README.md`: 評価ワークスペースの入口、データ機密性ルール
- `docs/テスト設計.md`: raw → document_manifest → golden → generated のテスト構成
- `docs/単票評価ワークフローまとめ.md`: 単票fixture → Chrome拡張投入までの全体像
- `docs/AIブラインド抽出実行手順.md`: goldenを見せずにAI抽出を実行する手順
- `docs/フォルダ整理案.md`: test_cases_from_raw / blind_runs_from_test_cases / eval_config の役割分担
- `eval_config/suites/single_smoke.json`: 13ケースのスモーク評価スイート
- `eval_config/prompts/blind_single_case_prompt.md`: AI抽出時のプロンプトテンプレート

## PII・gitルール

- **git管理する**: `README.md`, `test_cases_from_raw/README.md`, `eval_config/suites/*.json`, `eval_config/prompts/`, `docs/`
- **git管理しない**: `raw/`, `catalog.json`, `test_cases_from_raw/<case_id>/`, `blind_runs_from_test_cases/`, `**/generated/`
- 実PIIを含むファイルはローカル管理のみ。バグ報告・チャットではPIIを伏せる。

## 評価実行の流れ

1. `rasens-autofill/scripts/prepare_blind_eval_run.py` でブラインド実行ディレクトリを作成
2. Codex/AIエージェントで `blind_runs_from_test_cases/<run_id>/` 内の資料から `case_data.json`, `review.json` を抽出
3. `rasens-autofill/scripts/build_application_data.py` で `application_data.json` を決定論的に生成
4. `expected/*.golden.json` と比較して精度を検証
