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

通常の評価は次の2コマンドで実行します。project 内の Python を使うため、基本は `visa-app/backend/.venv/bin/python` を使います。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py \
  <fixture_dir> \
  --output-dir <run_output>

visa-app/backend/.venv/bin/python visa-eval/scripts/compare_with_golden.py \
  --generated <run_output> \
  --expected <fixture_dir>/expected \
  --targets case_data
```

`<fixture_dir>` は `visa-eval/test_cases_from_raw/<case_id>/<applicant_id>` です。`<run_output>` は `generated/<run_id>` のような実行ごとの出力先を推奨します。

`compare_with_golden.py` の generated 側は `case_data.json` を必須にします。`case_data.golden.json` は expected 側だけのファイルです。

`application_data` は保存済みgoldenを正本にせず、比較時に expected / generated の `case_data` から backend generator で生成します。MVP採点には含めず、generator/mapping確認が必要なときだけ明示的に実行します。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/compare_with_golden.py \
  --generated <run_output> \
  --expected <fixture_dir>/expected \
  --targets application_data
```

`--dry-run` は必須ではありません。初回、新しいfixture、大きいPDF、送信対象確認が必要な場合だけ、Gemini APIへ送る前の確認として使います。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py <fixture_dir> --dry-run
```

`field_metadata` は現時点では主に根拠レビュー用です。定量比較に含める場合は `compare_with_golden.py` に比較ロジックを追加します。

全体方針と実測結果の解釈は `../../visa-app/docs/008_eval_workflow/README.md` を参照します。

## Golden比較のMVP方針

MVPでは `expected/case_data.golden.json` を唯一の正本にします。

- `application_data` は expected / generated の `case_data` から比較時に生成します。
- `expected/application_data.golden.json` は旧成果物として残っていても、初期MVPの比較では使いません。
- `review.golden.json` は残しますが、初期MVPでは gate にしません。
- `field_metadata` は generated を人間が確認するだけで、初期MVPでは採点しません。
