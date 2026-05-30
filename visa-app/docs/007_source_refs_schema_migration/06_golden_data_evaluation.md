# 06 Golden data 評価 詳細作業計画

## 位置づけ

Golden data 評価は後回しにする。

理由は、現時点では実データの正解自体が揺れやすく、先に採点ロジックを作ると「測りやすいもの」を正にしてしまうリスクがあるためです。

ただし、将来 `source_ref` dict 化、PDF bbox 改善、XLSX cell anchor、DOCX block anchor が入ったあとに、何を成果物として残し、どこまでを自動比較し、どこからを人手確認にするかは今のうちに決めておく。

## 調査した現状

### visa-eval

`visa-eval` は、実資料を使う restricted evaluation workspace として既に整理されている。

| ファイル | 現状の役割 |
|---|---|
| `visa-eval/README.md` | PII制約、fixture構成、Golden作成/評価モードの入口 |
| `visa-eval/AGENTS.md` | `raw/`, `catalog.json`, `test_cases_from_raw/`, `generated/` をgit管理外にする方針 |
| `visa-eval/docs/fixture_contract.md` | `scenario.json`, `document_manifest.json`, `expected/`, `generated/` の契約 |
| `visa-eval/eval_config/suites/single_smoke.json` | 13ケースの smoke suite 定義 |
| `visa-eval/scripts/run_gemini_bytes_eval.py` | GCS/Firestoreを使わず、ローカルbytesから backend Gemini pipeline を実行 |
| `visa-eval/scripts/build_application_data.py` | `case_data.json` から backend generator で `application_data.json` を生成 |
| `visa-eval/scripts/compare_with_golden.py` | `case_data`, `review`, `application_data` のgolden比較 |

現行の `compare_with_golden.py` は、主に値比較のためのスクリプトです。

- `case_data`: nested JSON を dot path に flatten して比較する
- `review`: `missing_items`, `validation_errors`, `findings` などを set 的に比較する
- `application_data`: `canonical_path` ごとに `fill_value` / `display_value` を比較する
- `field_metadata`: 現時点では比較対象に入っていない

### visa-app

`visa-app` 側は、通常の自動テストと手動QAが分かれている。

| ファイル | 現状の役割 |
|---|---|
| `visa-app/QA_MANUAL.md` | 実ファイルを使った手動QA手順、PDFハイライト、source_refs、application-data確認 |
| `visa-app/backend/tests/test_gemini.py` | Gemini APIをモックした抽出・field_metadata生成の単体テスト |
| `visa-app/backend/tests/test_application_data.py` | canonical case_data から RASENS rows を生成するロジックの単体テスト |
| `visa-app/backend/tests/test_pdf_text.py` | PDF text extraction の単体テスト |
| `visa-app/backend/tests/test_docx_text.py` | DOCX text extraction の単体テスト |
| `visa-app/backend/tests/test_xlsx.py` | XLSX extraction の単体テスト |
| `visa-app/backend/tests/test_vision.py` | Vision OCR の単体テスト |

backend tests は、PIIを含まない小さな入力・モックを使う通常CI向けのテストとして扱う。

## 評価レイヤー

Golden data 評価は、4層に分ける。

| レイヤー | 比較対象 | 目的 | 自動比較 |
|---|---|---|---|
| A. 抽出値 | `case_data.golden.json` | 申請データの値が期待通りか見る | 将来実施 |
| B. レビュー指摘 | `review.golden.json` | 不足・矛盾・要確認が期待通りか見る | 将来実施 |
| C. 証跡 | `field_metadata.golden.json` | `document_id`, `page`, `text_quote`, `anchor`, `bbox` を見る | 後回し |
| D. 入力データ | `application_data.golden.json` | Chrome拡張へ渡す rows が期待通りか見る | 将来実施 |

最初から bbox の正解率を厳密に採点しない。bbox は人間の見え方に依存し、正解領域の作成コストも高い。

初期は `case_data` と `application_data` の比較を主にし、`field_metadata` は「証跡レビュー用の成果物」として残す。`source_ref` と anchor 構造が安定した後に、`field_metadata` の比較ロジックを追加する。

## PII制約

実案件データを使う Golden data は restricted test data として扱う。

| 対象 | 方針 |
|---|---|
| `visa-eval/raw/` | git管理しない。原資料としてローカル管理 |
| `visa-eval/catalog.json` | 実PIIを含みうるためgit管理しない |
| `visa-eval/test_cases_from_raw/<case_id>/` | fixture本体はgit管理しない |
| `expected/*.golden.json` | JSONでも実PIIを含むためgit管理しない |
| `generated/` | AI出力でPIIを含みうるためgit管理しない |
| QAスクリーンショット | `qa/screenshots/` 配下に置き、git管理しない |
| DevTools log / Network export | 実値を含む場合は共有しない |

通常CIや公開PRには実PIIを持ち込まない。CIに載せるのは、PIIを含まない unit test と合成データの schema/loadability check までにする。

## 最小ケース

最初から `single_smoke.json` の13ケースを正解化しない。

段階は次の順にする。

| Phase | ケース数 | 目的 |
|---|---:|---|
| Phase 0 | 1件 | 形式と運用を固める |
| Phase 1 | 3件 | applicant差分、会社書類共通、家族在住パターンを確認する |
| Phase 2 | 13件 | `single_smoke` 全体へ広げる |

Phase 0 は、既存QAでも使われている Amit Tamang ケースを軸にするのがよい。

Phase 1 の候補:

| 候補 | 目的 |
|---|---|
| `gijinkoku_a_company_round1__amit_tamang` | PDF/DOCX/XLSX/会社書類の基本導線 |
| `gijinkoku_a_company_round1__kushang_subba_limbu` | 同一会社書類で申請人差分の取り違えを検出 |
| `gijinkoku_a_company_round2_family_japan__sanjay_gautam` | 家族在住・メール文脈・不足確認の別パターン |

## 成果物

各 fixture は次の構成にする。

```text
visa-eval/test_cases_from_raw/<base_case_id>/<applicant_id>/
  scenario.json
  input/
    document_manifest.json
  expected/
    case_data.golden.json
    review.golden.json
    field_metadata.golden.json
    application_data.golden.json
  generated/
    <run_id>/
      case_data.json
      review.json
      field_metadata.json
      application_data.json
      comparison_report.md
```

### `case_data.golden.json`

value-only の canonical case_data を正とする。

- RASENSの `field_id`, `field_name`, select value は入れない
- 旧path互換を入れない
- 空欄でよい項目は空欄のまま残してよい
- 部分入力を許す方針なので、必須不足を機械的に失敗扱いしない

### `review.golden.json`

不足・矛盾・人間確認が必要な点を正とする。

ただし、自然文全文一致は避ける。将来的には `code`, `path`, `severity`, `reason` のような構造化に寄せる。

### `field_metadata.golden.json`

証跡レビュー用に残す。

初期は自動採点しない。将来、次の単位で比較する。

| 項目 | 初期扱い | 将来の比較 |
|---|---|---|
| `document_id` | 人手確認 | 一致比較 |
| `page` | 人手確認 | 一致比較 |
| `text_quote` | 人手確認 | 部分一致 / 正規化一致 |
| `anchor_type` | source_ref改善後に追加 | 一致比較 |
| `bbox` | PDF改善後に追加 | 人手確認またはIoU |
| `confidence` | 参考値 | 厳密比較しない |

### `application_data.golden.json`

AIに手書きさせない。`case_data.golden.json` から backend generator で生成した結果を正とする。

比較対象は次から始める。

- `canonical_path`
- `field_id`
- `field_name`
- `input_type`
- `fill_value`
- `display_value`
- rows の欠落・過剰

`visible_when` により出る/出ない行は、`application_data` 側の重要な比較対象にする。

## 作業計画

### Step 1. 現状契約の整理

- [ ] `visa-eval/docs/fixture_contract.md` に、`field_metadata.golden.json` は初期採点対象外であることを明記する
- [ ] `visa-eval/README.md` の Golden data 方針とこの文書の内容を揃える
- [ ] `visa-app/QA_MANUAL.md` に、手動QAと Golden data 評価の役割差を明記する

### Step 2. Phase 0 fixture の確定

- [ ] Amit Tamang ケースを Phase 0 として選ぶ
- [ ] `document_manifest.json` の `use_as_input` と `document_role` を確認する
- [ ] `generated/` を作り、Gemini bytes eval または blind run の出力を保存する
- [ ] 人手で `case_data.golden.json` を確定する
- [ ] backend generator で `application_data.golden.json` を生成する
- [ ] `field_metadata.golden.json` は採点せず、根拠レビュー用として保存する

### Step 3. 既存比較スクリプトの適用範囲を固定

- [ ] `compare_with_golden.py` は当面 `case_data`, `review`, `application_data` の比較に限定する
- [ ] `field_metadata` 比較は未実装のまま、将来TODOとして残す
- [ ] `application_data` 比較に `field_id`, `field_name`, `input_type`, rows欠落/過剰を含めるか検討する

### Step 4. Phase 1 へ拡張

- [ ] 3ケースに増やす
- [ ] 同一会社書類で applicant を取り違えないか確認する
- [ ] 家族在住・不足確認パターンを含める
- [ ] fixtureごとの `comparison_report.md` を残す

### Step 5. source_ref / anchor 改善後の追加評価

- [ ] `source_ref` dict 化後に `field_metadata.golden.json` の形式を更新する
- [ ] PDF bbox改善後に `bbox` の人手確認観点を追加する
- [ ] XLSX cell anchor 後に `sheet_name`, `cell` の比較を追加する
- [ ] DOCX block anchor 後に `paragraph_index` / `table_index` の比較を追加する

### Step 6. CI / restricted run の分離

- [ ] 通常CIには実PII fixtureを載せない
- [ ] 通常CIは backend unit tests と合成データの schema/loadability check に限定する
- [ ] Golden data 評価はローカルまたは restricted runner のみで実行する
- [ ] 実行ログ・レポート・スクリーンショットを外部共有しない

## 通常CIに載せない範囲

次は通常CIに載せない。

- `visa-eval/raw/`
- `visa-eval/catalog.json`
- `visa-eval/test_cases_from_raw/<case_id>/`
- `expected/*.golden.json`
- `generated/`
- 実資料を使った Gemini bytes eval
- 実資料を使った Codex blind run
- 実RASENS画面や実Chrome拡張での入力結果
- PIIを含むスクリーンショット・DevTools出力

通常CIに載せてよいものは次に限定する。

- `visa-app/backend/tests/*`
- PIIを含まない `application_data` generator の単体テスト
- schema loadability check
- 合成データの Chrome拡張 smoke test

## 意思決定ポイント

将来実装前に決めること。

| 論点 | 推奨 |
|---|---|
| Golden dataをいつ作るか | `source_ref` dict化とPDF bbox改善の後 |
| 最初の母数 | 1ケース |
| 最初に採点するもの | `case_data` と `application_data` |
| `field_metadata` の扱い | 初期は人手レビュー用、後で比較対象 |
| bboxの正解 | 初期は自動採点しない |
| CI | 実PIIは載せない |
| `application_data.golden.json` | AIではなく backend generator で生成 |

## いま実装しないこと

- `field_metadata` 比較ロジックの実装
- bbox IoU 採点
- DOCX/XLSX anchor 採点
- `single_smoke` 13ケースの一括golden化
- CIへの実案件fixture投入
- 実データを匿名化せずにgit管理すること
