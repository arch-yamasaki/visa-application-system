# Codexブラインド抽出実行手順

## 目的

この手順は、Codexに実PDF・Excel・Docx等を読ませて `generated/case_data.json`、`generated/field_metadata.json`、`generated/review.json` を作らせるためのものです。

Geminiを評価する場合は、この自由操作型の手順ではなく `visa-eval/scripts/run_gemini_bytes_eval.py` を使います。Gemini bytes eval は指定ファイルだけを backend の scoped Gemini 抽出pipelineへ渡すため、GCSやCloud Run Jobは不要です。

最重要ルールはこれです。

```text
AIに expected/*.golden.json を絶対に見せない。
```

goldenを見てしまうと、AIが資料から抽出できたのか、正解を写しただけなのか分からなくなります。そのため、AIにはfixture本体ではなく、`expected/` を含まない「ブラインド実行ディレクトリ」を渡します。

この運用では、プロンプトの禁止文は補助です。主対策は、AIの作業ディレクトリから `expected/` と `*.golden.json` を物理的に外すことです。

## 全体フロー

```text
test_cases_from_raw/<case>/<applicant>/
  scenario.json
  input/document_manifest.json
  expected/*.golden.json   <- AIには見せない

prepare_blind_eval_run.py
  -> visa-eval/blind_runs_from_test_cases/<run_id>/
       AGENT_TASK.md
       scenario.json
       document_manifest.blind.json
       documents/
       output_contract.md
       allowed_reference_paths.txt
       generated/

AI/Codex
  -> generated/case_data.json
  -> generated/field_metadata.json
  -> generated/review.json
  -> generated/run_notes.md

build_application_data.py
  -> generated/application_data.json

人間レビュー
  -> expected/*.golden.json と比較
```

## 1. ブラインド実行ディレクトリを作る

例:

```bash
python visa-eval/scripts/prepare_blind_eval_run.py \
  visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang
```

出力例:

```text
visa-eval/blind_runs_from_test_cases/20260509_153000_gijinkoku_a_company_round1__amit_tamang/
  AGENT_TASK.md
  scenario.json
  document_manifest.blind.json
  allowed_reference_paths.txt
  output_contract.md
  documents/
    doc_001.docx
    doc_002.pdf
    doc_003.pdf
    doc_004.xlsx
    doc_005.pdf
  generated/
```

`documents/` は元資料のコピーです。AIにはこのrunディレクトリの中だけを入口として渡します。

run用の `scenario.json` からは、`expected_case_data`、`expected_application_data`、`expected_review` の参照を落とします。fixture本体の `scenario.json` にはexpectedパスが入っているため、AIにはfixture本体を渡さないでください。

## 2. codex exec でローカル実行する

`codex exec` を使うと、ブラインド run ディレクトリを作業ディレクトリとして AI 抽出をローカルで実行できる。

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

`<run_id>` は手順1で生成されるディレクトリ名（例: `20260512_114953_gijinkoku_a_company_round1__amit_tamang`）に置き換える。

`-C` オプションで run ディレクトリを作業ディレクトリに指定するため、AI は `expected/` にアクセスできない。

`generated/case_data.json` は value-only の canonical path に統一します。配列pathは `applicant.education.0.school_name` の dot index 形式を使い、`application.*`, top-level `passport.*`, `employment_conditions.*` は出力しません。`generated/application_data.json` はAIが手書きせず、backend generator の出力として作ります。

## 3. AIに渡すもの

AIに渡す入口は、runディレクトリの `AGENT_TASK.md` です。

AIへの依頼文の例:

```text
以下のブラインド実行ディレクトリだけを使って、在留資格申請の抽出を実行してください。

<run_dir>/AGENT_TASK.md を読んでください。
expected/ や *.golden.json は絶対に読まないでください。
出力は <run_dir>/generated/ にだけ作成してください。
```

AIに渡してよいファイル:

- `AGENT_TASK.md`
- `scenario.json`
- `document_manifest.blind.json`
- `documents/*`
- `output_contract.md`
- `allowed_reference_paths.txt`
- `rasens-autofill/data/schemas/review.schema.json`
- `rasens-autofill/data/schemas/document_manifest.schema.json`
- `visa-app/docs/002_review_field_order/canonical_case_data_v2.md`
- `visa-app/frontend/src/types/caseData.ts`
- `rasens-autofill/data/mappings/rasens_offer_mapping_v2.json`
- `rasens-autofill/data/form_definitions/rasens_offer_fields.json`
- backend generator または `visa-eval/scripts/build_application_data.py`

AIに渡してはいけないファイル:

- fixture本体の `scenario.json`
- `visa-eval/test_cases_from_raw/**/expected/**`
- `*.golden.json`
- 他runの `generated/**`
- 実案件入りの `rasens-autofill/extension/application_data.json`
- 提出済み申請書PDF（`submitted_application_pdf`）

提出済み申請書PDF（`submitted_application_pdf`）はAIブラインド抽出のインプットではない。これはgolden正解データの根拠として使用するものであり、AIには読ませない。`document_manifest.json` で `"use_as_input": false` が設定されており、`prepare_blind_eval_run.py` はこれらをrunディレクトリの `documents/` にコピーしない。

## 4. AIが作る出力

AIが作るのは次の4ファイルです。

```text
generated/case_data.json
generated/field_metadata.json
generated/review.json
generated/run_notes.md
```

`generated/case_data.json` は、資料から読み取った正規化データです。

`generated/field_metadata.json` は、各フィールドの根拠資料・ページ・短い引用・confidenceです。`case_data.json` の中には入れません。

`generated/review.json` は、不足項目、読み取り不確実、矛盾、人手確認が必要な点です。

`generated/run_notes.md` は、どの資料を読んだか、どこが弱いか、次に人間が見るべき点のメモです。個人情報を長く貼り付けず、項目名と判断理由中心にします。

AIに `generated/application_data.json` を手作業で作らせません。フォーム投入用JSONは backend generator で deterministic に生成します。

## 5. application_dataを生成する

AIが `generated/case_data.json` を作った後、`build_application_data.py` が backend generator を呼び、Chrome拡張と同じ形式のフォーム投入用行配列を生成します。

```bash
python visa-eval/scripts/build_application_data.py \
  visa-eval/blind_runs_from_test_cases/<run_id>/generated/case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping_v2.json \
  visa-eval/blind_runs_from_test_cases/<run_id>/generated/application_data.json
```

## 6. 人間レビューでgoldenと比較する

比較はAIが終わった後に行います。まずスクリプトで機械比較し、その後に人間が `run_notes` と差分を確認します。

```bash
python visa-eval/scripts/compare_with_golden.py \
  --generated visa-eval/blind_runs_from_test_cases/<run_id>/generated \
  --expected visa-eval/test_cases_from_raw/<case_id>/<applicant_id>/expected
```

見る順番:

1. `generated/run_notes.md`
2. `generated/review.json`
3. `generated/case_data.json`
4. `generated/field_metadata.json`
5. `generated/application_data.json`
6. `expected/*.golden.json`

この順番にする理由は、最初からgoldenを見ると評価者側もAIの抽出ミスを見落としやすくなるためです。

比較観点:

- 入力資料だけから取れる値が取れているか。
- Excelにある値だけで止まっていないか。
- PDF、雇用条件通知書、会社書類から補完できているか。
- 不明な項目を勝手に推測していないか。
- `review.json` に不足・不確実・人手確認が出ているか。
- 技人国として、学歴・職務・活動内容のつながりを確認しているか。
- `application_data.json` の行がフォーム台帳・マッピングに沿っているか。

## 7. 漏えい防止チェック

AI実行前:

- runディレクトリに `expected/` が存在しないこと。
- runディレクトリの `scenario.json` に `expected_` で始まるキーがないこと。
- `document_manifest.blind.json` が `documents/` 配下だけを指していること。
- AIへの依頼文に `expected/` と `*.golden.json` 禁止が明記されていること。
- `generated/` が空、または今回run用に初期化されていること。

AI実行中:

- AIが `expected`、`golden`、他runの `generated` を検索しようとしたら中止する。
- AIが値を推測した場合は、`review.json` の不足・不確実に戻す。
- チャットやログに旅券番号、住所、電話、メールなどを貼らない。

AI実行後:

- `generated/` をrestricted dataとして扱う。
- `generated/` をgitに入れない。
- Chrome確認に使ったら `chrome.storage.local` を削除する。
- bug報告では実値をマスクする。

## 8. 推奨するAI依頼文

```text
あなたは在留資格申請の単票ケースを抽出するAIエージェントです。

作業ディレクトリ:
<run_dir>

最初に <run_dir>/AGENT_TASK.md を読んでください。

絶対ルール:
- expected/ を読まない。
- *.golden.json を読まない。
- 他の generated/ を読まない。
- 値を推測しない。
- 出力は <run_dir>/generated/ にだけ作る。

やること:
1. scenario.json と document_manifest.blind.json を読む。
2. documents/ 配下の資料だけを読む。
3. generated/case_data.json を作る。
4. generated/field_metadata.json を作る。
5. generated/review.json を作る。
6. generated/run_notes.md を作る。
7. application_data.json は手作業で作らない。
```

## 9. 失敗パターン

| 失敗 | 何が問題か | 対策 |
| --- | --- | --- |
| AIが `expected/case_data.golden.json` を読む | 正解を写せるため評価不能 | runディレクトリだけ渡す。禁止文を明記する。 |
| AIがExcelだけ見てPDFを読まない | 実運用で足りない項目が抜ける | `documents/` 全件を読んだメモを `run_notes.md` に書かせる。 |
| 不明値を推測する | 実申請で危険 | 不明は空欄・`null`・`review.missing_items` にする。 |
| `application_data` をAIが手書きする | マッピング検証と混ざる | backend generator で生成する。 |
| Consoleやチャットに実値を貼る | PII漏えい | 出力JSON内だけに保持し、共有時はマスクする。 |
| Chrome拡張に実データを残す | 次案件へ混線する | 専用Chromeプロファイルと `chrome.storage.local` 削除を徹底する。 |

## 10. expected の扱い

`prepare_blind_eval_run.py` は、runディレクトリに `expected/` をコピーしません。run用の `scenario.json` からも `expected_case_data`、`expected_application_data`、`expected_review` の参照を落とします。

評価スクリプトやレビュー担当者は、AI実行後に元fixture側の `expected/` を明示指定して比較します。
