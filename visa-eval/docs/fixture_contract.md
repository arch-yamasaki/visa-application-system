# Fixture Contract

`test_cases_from_raw/<case_id>/<applicant_id>/` は、1申請人=1フォームの評価fixtureです。

## Inputs

- `scenario.json`: ケースID、申請種別、対象在留資格などの評価メタデータ。
- `input/document_manifest.json`: AIへ渡す候補資料。`use_as_input: true` の資料だけを抽出入力に使う。
- `expected/`: 人手確認済みのgolden。AIやGeminiへは渡さない。

## Generated Outputs

- `generated/case_data.json`: value-only canonical v2 case data。
- `generated/field_metadata.json`: canonical v2 dot pathごとの根拠情報。`case_data.json` には入れない。
- `generated/review.json`: 欠損、矛盾、不確実、人手確認事項。
- `generated/application_data.json`: `case_data.json` から backend generator が生成するフォーム投入用JSON。AIが手書きしない。

## Execution Flows

- Codex blind run: `prepare_blind_eval_run.py` が `expected/` を除外したrunディレクトリを作り、Codexが資料を読んで `case_data`, `field_metadata`, `review`, `run_notes` を作る。
- Gemini bytes eval: `run_gemini_bytes_eval.py` が指定ファイルをbytesとして読み、GCS/Firestoreを使わず backend の scoped Gemini 抽出pipelineへ渡す。

### Gemini Bytes Eval

通常の評価は次の3コマンドで実行します。

```bash
python visa-eval/scripts/run_gemini_bytes_eval.py \
  <fixture_dir> \
  --output-dir <run_output>

python visa-eval/scripts/build_application_data.py \
  <run_output>/case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping_v2.json \
  <run_output>/application_data.json

python visa-eval/scripts/compare_with_golden.py \
  --generated <run_output> \
  --expected <fixture_dir>/expected
```

`<fixture_dir>` は `visa-eval/test_cases_from_raw/<case_id>/<applicant_id>` です。`<run_output>` は `generated/<run_id>` のような実行ごとの出力先を推奨します。

`--dry-run` は必須ではありません。初回、新しいfixture、大きいPDF、送信対象確認が必要な場合だけ、Gemini APIへ送る前の確認として使います。

```bash
python visa-eval/scripts/run_gemini_bytes_eval.py <fixture_dir> --dry-run
```

`field_metadata` は現時点では主に根拠レビュー用です。定量比較に含める場合は `compare_with_golden.py` に比較ロジックを追加します。
