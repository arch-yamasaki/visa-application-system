# AIブラインド抽出実行手順

## 目的

この手順は、AIに実PDF・Excel・Docx等を読ませて `generated/case_data.json` と `generated/review.json` を作らせるためのものです。

最重要ルールはこれです。

```text
AIに expected/*.golden.json を絶対に見せない。
```

goldenを見てしまうと、AIが資料から抽出できたのか、正解を写しただけなのか分からなくなります。そのため、AIにはfixture本体ではなく、`expected/` を含まない「ブラインド実行ディレクトリ」を渡します。

この運用では、プロンプトの禁止文は補助です。主対策は、AIの作業ディレクトリから `expected/` と `*.golden.json` を物理的に外すことです。

## 全体フロー

```text
fixtures_single/<case>/<applicant>/
  scenario.json
  input/input_documents.json
  expected/*.golden.json   <- AIには見せない

prepare_blind_eval_run.py
  -> visa-eval/runs/<run_id>/
       AGENT_TASK.md
       scenario.json
       input_documents.blind.json
       documents/
       output_contract.md
       allowed_reference_paths.txt
       generated/

AI/Codex
  -> generated/case_data.json
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
python3 rasens-autofill/scripts/prepare_blind_eval_run.py \
  visa-eval/fixtures_single/gijinkoku_a_company_round1/amit_tamang
```

出力例:

```text
visa-eval/runs/20260509_153000_gijinkoku_a_company_round1__amit_tamang/
  AGENT_TASK.md
  scenario.json
  input_documents.blind.json
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

`documents/` は元資料へのsymlinkです。資料を複製せず、AIにはこのrunディレクトリの中だけを入口として渡します。

run用の `scenario.json` からは、`expected_case_data`、`expected_application_data`、`expected_review` の参照を落とします。fixture本体の `scenario.json` にはexpectedパスが入っているため、AIにはfixture本体を渡さないでください。

## 2. AIに渡すもの

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
- `input_documents.blind.json`
- `documents/*`
- `output_contract.md`
- `allowed_reference_paths.txt`
- `rasens-autofill/data/schemas/case_data.schema.json`
- `rasens-autofill/data/schemas/review.schema.json`
- `rasens-autofill/data/schemas/input_documents.schema.json`
- `rasens-autofill/data/mappings/rasens_offer_mapping.json`
- `rasens-autofill/data/form_definitions/rasens_offer_fields.json`
- `rasens-autofill/scripts/build_application_data.py`

AIに渡してはいけないファイル:

- fixture本体の `scenario.json`
- `visa-eval/fixtures_single/**/expected/**`
- `*.golden.json`
- 他runの `generated/**`
- 実案件入りの `rasens-autofill/extension/application_data.json`

## 3. AIが作る出力

AIが作るのは次の3ファイルです。

```text
generated/case_data.json
generated/review.json
generated/run_notes.md
```

`generated/case_data.json` は、資料から読み取った正規化データです。

`generated/review.json` は、不足項目、読み取り不確実、矛盾、人手確認が必要な点です。

`generated/run_notes.md` は、どの資料を読んだか、どこが弱いか、次に人間が見るべき点のメモです。個人情報を長く貼り付けず、項目名と判断理由中心にします。

AIに `generated/application_data.json` を手作業で作らせません。フォーム投入用JSONは deterministic に生成します。

## 4. application_dataを生成する

AIが `generated/case_data.json` を作った後、人間またはスクリプトで次を実行します。

```bash
python3 rasens-autofill/scripts/build_application_data.py \
  <run_dir>/generated/case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping.json \
  <run_dir>/generated/application_data.json
```

これで、Chrome拡張と同じ形式のフォーム投入用行配列ができます。

## 5. 人間レビューでgoldenと比較する

比較はAIが終わった後に、人間が行います。

見る順番:

1. `generated/run_notes.md`
2. `generated/review.json`
3. `generated/case_data.json`
4. `generated/application_data.json`
5. `expected/*.golden.json`

この順番にする理由は、最初からgoldenを見ると評価者側もAIの抽出ミスを見落としやすくなるためです。

比較観点:

- 入力資料だけから取れる値が取れているか。
- Excelにある値だけで止まっていないか。
- PDF、雇用条件通知書、会社書類から補完できているか。
- 不明な項目を勝手に推測していないか。
- `review.json` に不足・不確実・人手確認が出ているか。
- 技人国として、学歴・職務・活動内容のつながりを確認しているか。
- `application_data.json` の行がフォーム台帳・マッピングに沿っているか。

## 6. 漏えい防止チェック

AI実行前:

- runディレクトリに `expected/` が存在しないこと。
- runディレクトリの `scenario.json` に `expected_` で始まるキーがないこと。
- `input_documents.blind.json` が `documents/` 配下だけを指していること。
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

## 7. 推奨するAI依頼文

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
1. scenario.json と input_documents.blind.json を読む。
2. documents/ 配下の資料だけを読む。
3. generated/case_data.json を作る。
4. generated/review.json を作る。
5. generated/run_notes.md を作る。
6. application_data.json は手作業で作らない。
```

## 8. 失敗パターン

| 失敗 | 何が問題か | 対策 |
| --- | --- | --- |
| AIが `expected/case_data.golden.json` を読む | 正解を写せるため評価不能 | runディレクトリだけ渡す。禁止文を明記する。 |
| AIがExcelだけ見てPDFを読まない | 実運用で足りない項目が抜ける | `documents/` 全件を読んだメモを `run_notes.md` に書かせる。 |
| 不明値を推測する | 実申請で危険 | 不明は空欄・`null`・`review.missing_items` にする。 |
| `application_data` をAIが手書きする | マッピング検証と混ざる | `build_application_data.py` で生成する。 |
| Consoleやチャットに実値を貼る | PII漏えい | 出力JSON内だけに保持し、共有時はマスクする。 |
| Chrome拡張に実データを残す | 次案件へ混線する | 専用Chromeプロファイルと `chrome.storage.local` 削除を徹底する。 |
