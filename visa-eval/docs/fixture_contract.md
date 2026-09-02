# Fixture Contract

`test_cases_from_raw/<case_id>/<applicant_id>/` は、1申請人=1フォームの評価fixtureです。

## Inputs

- `scenario.json`: ケースID、申請種別、対象在留資格などの評価メタデータ。
- `input/document_manifest.json`: AIへ渡す候補資料。`use_as_input: true` の資料だけを抽出入力に使う。
- `output/output_manifest.json`: RASENS入力済み申請書など、golden作成・監査で使う資料。AIやGeminiへは渡さない。
- `expected/`: 既存の旧golden。内容を変更せず保存し、AIやGeminiへは渡さない。
- `expected_verified/`: 新しい比較用の値ファイルと `golden_manifest.json`。初期値は旧goldenと同一で、AIやGeminiへは渡さない。

## Generated Outputs

- `eval_runs/<run_id>/<case_id>/case_data.json`: value-only canonical v2 case data。
- `eval_runs/<run_id>/<case_id>/field_metadata.json`: canonical v2 dot pathごとの根拠情報。`case_data.json` には入れない。
- `eval_runs/<run_id>/<case_id>/review.json`: 欠損、矛盾、不確実、人手確認事項。
- `eval_runs/<run_id>/<case_id>/application_data.json`: `case_data.json` から backend generator が生成するフォーム投入用JSON。AIが手書きしない。

## Execution Flows

- Codex blind run: `prepare_blind_eval_run.py` がgoldenを含めずrunディレクトリを作り、Codexが資料を読んで `case_data`, `field_metadata`, `review`, `run_notes` を作る。
- Gemini bytes eval: `run_gemini_bytes_eval.py` が指定ファイルをbytesとして読み、GCS/Firestoreを使わず backend の scoped Gemini 抽出pipelineへ渡す。

提出済み申請書PDFに RASENS 出力ページと添付資料ページが混ざる場合は、事前に物理分割します。RASENS 出力ページは `output/rasens_application/`、添付資料ページは必要に応じて `input/submitted_application_attachments/` に置きます。前者は golden 監査用、後者は Gemini 入力用です。

fixtureの作り方は `manual_fixture_creation.md` を参照します。

### Gemini Bytes Eval

通常の評価は次の2コマンドで実行します。project 内の Python を使うため、基本は `visa-app/backend/.venv/bin/python` を使います。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py \
  <fixture_dir> \
  --run-id <run_id>

visa-app/backend/.venv/bin/python visa-eval/scripts/compare_with_golden.py \
  --generated <run_output> \
  --expected <fixture_dir>/expected_verified \
  --targets case_data
```

`<fixture_dir>` は `visa-eval/test_cases_from_raw/<case_id>/<applicant_id>` です。`<run_output>` は通常 `visa-eval/eval_runs/<run_id>/<case_id>` です。`--output-dir` を明示した場合だけ任意の出力先に書きます。

`compare_with_golden.py` の generated 側は `case_data.json` を必須にします。`case_data.golden.json` は expected 側だけのファイルです。`golden_manifest.json` がある場合は、verifiedな `extraction` fieldだけを採点します。

`application_data` は保存済みgoldenを正本にせず、比較時に expected / generated の `case_data` から backend generator で生成します。MVP採点には含めず、generator/mapping確認が必要なときだけ明示的に実行します。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/compare_with_golden.py \
  --generated <run_output> \
  --expected <fixture_dir>/expected_verified \
  --targets application_data
```

`--dry-run` は必須ではありません。初回、新しいfixture、大きいPDF、送信対象確認が必要な場合だけ、Gemini APIへ送る前の確認として使います。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py <fixture_dir> --dry-run
```

`field_metadata` は現時点では主に根拠レビュー用です。定量比較に含める場合は `compare_with_golden.py` に比較ロジックを追加します。

比較器自体の軽い確認は、pytestではなく通常のPythonスクリプトで実行します。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/check_compare_with_golden.py
```

全体方針と実測結果の解釈は `../../visa-app/docs/008_eval_workflow/README.md` を参照します。

## Golden比較のMVP方針

新しい検証では `expected_verified/case_data.golden.json` を値の正本にし、`golden_manifest.json` で採点対象を決めます。既存の `expected/case_data.golden.json` は旧データとして変更しません。

- `application_data` は expected / generated の `case_data` から比較時に生成します。
- `expected/application_data.golden.json` は旧成果物として残っていても、初期MVPの比較では使いません。
- `review.golden.json` は残しますが、初期MVPでは gate にしません。
- `field_metadata` は generated を人間が確認するだけで、初期MVPでは採点しません。

## 採点対象fieldの内部値契約

`case_data` 自体を内部統一形式とし、別の `canonical_case_data` ファイルは作りません。比較器で吸収するのは、NFKC、余分な空白、明白な同義ラベル、同じ完全日付の区切り文字差だけです。住所要素の欠落、識別番号の桁違い、年月と年月日の差、意味カテゴリの差は一致にしません。

- `applicant.sex`: `male` / `female`
- `applicant.marital_status`: `single` / `married`
- `applicant.occupation`: 申請人の現在の職業・身分。採用後の予定業務を入れない
- `applicant.birth_place`, `applicant.home_country_address`, `employer.address`: 原資料にない国名・住所要素を追加せず、出生地・本国現住所・会社所在地を混同しない。RASENSにしかない会社住所の追加粒度は `application_only`
- `employer.corporate_number`: input上で法人番号として明示された、記号除去後の13桁のみ。12桁を補完しない。`has_corporate_number` は番号本体からの派生値として独立採点しない
- `employment.joining_date`: 完全な `YYYY-MM-DD` のみ。年月しかない場合に日を補完しない
- `employment.job_category_primary`: 現行RASENSの職種選択肢と完全一致するラベル。現在職 `applicant.occupation` と混同しない
- `employment.position_title`: 組織上の正式な地位・役職名だけ。職種・担当業務は入れない
- `employment.has_position`: `position_title` からの派生値。実在する役職名がある場合だけ `true` とし、独立採点しない
- `applicant.education[].level`: アプリ用学歴区分。学位の原文は重複して入れない
- `applicant.education[].major_field`: アプリ用専攻分野区分。`major_field_other` は「その他」の補足が必要な場合だけ使う

`expected_verified` をAI出力へ合わせて変更してはいけません。原資料、申請済み出力、現行アプリの選択肢・変換規則を確認し、golden側の誤りが確定した場合だけrevisionを更新します。旧 `expected/` は変更しません。
