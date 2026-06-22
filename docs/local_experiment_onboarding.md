# ローカル実験オンボーディング

この文書は、このリポジトリをローカルで動かして、実資料ベースの抽出評価や画面QAを始めるための入口です。

対象は `visa-app`, `visa-eval`, `rasens-autofill` をまたぐ実験です。実案件由来の資料を扱うため、ここで扱うZIP、fixture、実行結果、スクリーンショットは `restricted test data` として扱います。

## 全体像

```text
visa-eval/
  raw/                         # 受領した原資料。git管理外
  test_cases_from_raw/          # 評価用に整理した単票fixture。git管理外
  eval_runs/                    # Gemini bytes eval の実行結果。git管理外
  blind_runs_from_test_cases/   # Codex blind run の一時作業領域。git管理外

qa/
  test-files/                   # 手動UI QA用アップロードファイル。git管理外
  screenshots/                  # QAスクリーンショット。git管理外
```

`raw/` は原本置き場です。評価スクリプトが直接読む中心は `test_cases_from_raw/<case_id>/<applicant_id>/input/document_manifest.json` に書かれた `path` です。

## 必要なZIP

ローカル実験用には、次の2種類を分けます。

| ZIP | 用途 | 必須度 |
| --- | --- | --- |
| `visa-eval-raw-YYYYMMDD.zip` | active fixtureが参照する受領原本の保管、fixture再作成、ページ分割の見直し | 既存fixtureを回すだけなら任意 |
| `visa-eval-fixtures-active-YYYYMMDD.zip` | 既存evalをすぐ実行できる単票fixture一式 | 必須 |

raw ZIPだけでは、既存evalをすぐ回せるとは限りません。`document_manifest.json` が参照する相対パスに、整理済みの入力ファイルとgoldenが置かれている必要があります。

Desktopは受け渡しの一時置き場です。展開後はワークスペース配下に集約し、不要なZIPや複製は残しっぱなしにしないでください。

## Fixture ZIPの構成

ZIPはリポジトリルートで展開して、そのまま相対パスが一致する形にします。

```text
visa-eval/test_cases_from_raw/<case_id>/<applicant_id>/
  scenario.json
  input/
    document_manifest.json
    files/
      offer_letter_translated.docx
      offer_letter_[MASKED].pdf
      intake.xlsx
      company_docs.pdf
    submitted_application_attachments/
      submitted_bundle_[MASKED].pdf
  expected/
    case_data.golden.json
  output/
    output_manifest.json
    rasens_application/
      submitted_form_[MASKED].pdf
```

既存のactive fixtureでは、`expected/case_data.golden.json` をMVP評価の正本として扱います。`application_data` は `case_data` からbackend generatorで生成する派生物なので、ZIPに含めなくて構いません。

## 展開先

fixture ZIPはリポジトリルートで展開します。

```bash
cd "/Users/yohei/Documents/1.起業/31. 在留資格申請"
unzip ~/Desktop/visa-eval-fixtures-active-YYYYMMDD.zip
```

raw ZIPを使う場合は、`visa-eval/raw/` に置きます。

```bash
mkdir -p visa-eval/raw
cp ~/Desktop/visa-eval-raw-YYYYMMDD.zip visa-eval/raw/申請書類.zip
```

raw ZIPは受領原本のarchiveとして扱い、加工しません。raw ZIPを展開してfixtureを作り直す場合は、評価用コピーや分割PDFを `test_cases_from_raw/` 側に作ります。詳しくは `visa-eval/docs/manual_fixture_creation.md` を参照します。

## 評価実行

Gemini bytes evalは、fixtureディレクトリを指定して実行します。backendのPythonは project-local venv を使います。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py \
  visa-eval/test_cases_from_raw/<case_id>/<applicant_id> \
  --run-id <run_id>

visa-app/backend/.venv/bin/python visa-eval/scripts/compare_with_golden.py \
  --generated visa-eval/eval_runs/<run_id>/<case_id> \
  --expected visa-eval/test_cases_from_raw/<case_id>/<applicant_id>/expected \
  --targets case_data
```

初回や新しいfixtureでは、送信対象の確認として `--dry-run` を使います。

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py \
  visa-eval/test_cases_from_raw/<case_id>/<applicant_id> \
  --dry-run
```

Codex blind runを使う場合は、`visa-eval/scripts/prepare_blind_eval_run.py` で `expected/` を除外したrunディレクトリを作ってから実行します。AIに `expected/*.golden.json` を見せず、出力は `eval_runs/` または blind run の `generated/` にだけ出します。

MVPの採点正本は `expected/case_data.golden.json` です。`application_data` は `case_data` からbackend generatorで生成する派生物で、AIに手書きさせません。`field_metadata` は主に根拠レビュー用、`review` は人手確認事項の補助として扱います。

## UI QA用データ

フロント画面からアップロードして確認する場合は、評価fixtureとは別に `qa/test-files/` へテスト用ファイルを置きます。

```text
qa/test-files/
  offer_letter_[MASKED].pdf
  offer_letter_translated.docx
  company_docs.pdf
  intake.xlsx
```

手動QAの詳細は `visa-app/QA_MANUAL.md` を参照します。

実データで画面確認した後は、専用Chromeプロファイルの `chrome.storage.local` を消去します。スクリーンショットは `qa/screenshots/` に置き、gitには入れません。

## Git管理とPII

以下はgitに入れません。

- `visa-eval/raw/`
- `visa-eval/test_cases_from_raw/<case_id>/`
- `visa-eval/eval_runs/<run_id>/`
- `visa-eval/blind_runs_from_test_cases/<run_id>/`
- `qa/`
- `rasens-autofill/extension/application_data.json`

実案件由来の値をチャット、issue、bug reportに貼る場合は、氏名、住所、電話、メール、旅券番号、申請番号、自由記述を伏せます。

## チェックリスト

- [ ] fixture ZIPをリポジトリルートで展開した
- [ ] `input/document_manifest.json` の `path` が実ファイルに解決できる
- [ ] `expected/case_data.golden.json` がある
- [ ] `--dry-run` で送信対象を確認した
- [ ] 実行結果は `visa-eval/eval_runs/` に出している
- [ ] 実PII入りZIPやスクリーンショットをgitに入れていない
