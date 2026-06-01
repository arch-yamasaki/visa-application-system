# Eval workflow

## 目的

このディレクトリは、実資料fixtureを使った Gemini 抽出評価の進め方を管理します。

目的はスコアを高く見せることではなく、次の問いを分けて判断できるようにすることです。

```text
1. golden data は expected として使えるだけ正しいか
2. Gemini は入力資料から canonical case_data を正しく抽出できたか
3. backend は case_data から Chrome拡張用 application_data rows を生成できるか
4. mismatch は Gemini の抽出ミス、golden不足、比較正規化不足、mapping/generator差分のどれか
```

source_ref、bbox、Office anchor、retry loop の実装計画は `../007_source_refs_schema_migration/` に置きます。
この `008_eval_workflow/` は、evalの走らせ方と結果の読み方だけを扱います。

## 現時点の重要な発見

以前出ていた3ケースの `100.0%` は、Gemini抽出精度ではありません。

これは expected data を expected data と比較した smoke check です。

```text
expected/case_data.golden.json
  -> compare_with_golden.py
expected/case_data.golden.json
  = 100%
```

この確認は、fixtureと比較スクリプトが読めることを見るためには有効です。
ただし、抽出精度として報告してはいけません。

実Gemini出力を現在の golden と比較した暫定結果は次の通りです。

| Case | 暫定の機械比較一致率 |
|---|---:|
| `amit_tamang` | 70.6% (36/51) |
| `kushang_subba_limbu` | 69.8% (37/53) |
| `sanjay_gautam` | 70.6% (36/51) |

この数字も最終的なモデル品質ではありません。
golden不足と比較正規化不足が混ざっています。

## 評価タイプを分ける

すべてを1つの「精度」にまとめないでください。

| 種類 | 答える問い | 例 | モデル精度と呼べるか |
|---|---|---|---|
| Smoke check | fixtureと比較器が動くか | `expected` vs `expected` | 呼べない |
| 抽出比較 | Gemini出力が現在のgoldenと合うか | `generated/<run_id>` vs `expected` | 暫定のみ |
| Golden監査 | expected自体が資料に照らして正しいか | raw XLSX/DOCX/PDF vs `case_data.golden.json` | 呼べないが必須 |
| 根拠レビュー | 値の出典を追えるか | `field_metadata`, source quote, bbox | 呼べない |
| application rows確認 | Chrome拡張用rowsが作れるか | `case_data` -> `application_data` | 呼べない。mapping/generatorを含む |

レポートや会話では、次のように呼び分けます。

```text
Smoke一致率
機械比較一致率
人手確認後の抽出正答率
```

golden監査と比較正規化が済むまでは、単に「精度」とは呼ばない方が安全です。

## 既知の問題

### 1. golden がまだ薄い

最初の3ケースでは、`case_data.golden.json` は申請人基本情報、旅券、学歴、少量の入国計画を中心に入っています。
一方で、`employment` は未整備で、`employer` もほぼ `name` だけのケースがあります。

Gemini は雇用開始日、月給、役職、法人番号、売上、従業員数などを抽出しています。
しかし golden にそれらがないため、比較レポートでは「過剰抽出」として出ます。

これは自動的に Gemini の問題ではありません。
多くは golden completeness の問題です。

### 2. 比較ロジックが厳しすぎる箇所がある

意味は同じでも、表記差で mismatch になります。

| 意味 | Golden | Gemini | 現在の判定 |
|---|---|---|---|
| 無 | `False` / `無` | `No` | mismatch |
| ネパール | `ネパール Nepal` | `NEPAL` / `Nepal` | mismatch |
| 独身 | `single` | `SINGLE` / `Single` | mismatch |
| 雇用 | `雇用 Employment` | `雇用` | `display_value`差で mismatch |

比較レイヤーには、boolean、国名、enum、表示ラベルの小さく明示的な正規化ルールが必要です。

### 3. 本当の Gemini ミス候補もある

すべてが比較ノイズではありません。

例: Sanjay の XLSX には marital status が `Married` とありますが、ある Gemini 出力では `Single` になりました。
これは、元資料確認が終わるまでは実ミス候補として扱います。

### 4. submitted application PDF は正解監査用であり、Gemini入力ではない

`submitted_application_pdf` は、最終的にRASENSへ入力された内容に近い正解資料として扱います。
そのため、Geminiやblind agentには渡しません。

```text
submitted_application_pdf
  = 最終提出値の一次監査資料
  = goldenの正しさを確認する資料
  = Gemini入力には使わない

XLSX / DOCX / company_documents
  = Gemini入力資料
  = その値をGeminiが抽出できるはずかを判断する資料
```

PDFにだけ存在し、Gemini入力資料に存在しない値は、Geminiの抽出ミスとして扱いません。
その場合は、固定値、手入力値、または入力資料不足として分類します。

### 5. PDFは通常テキスト抽出だけでは確認しづらい

一部PDFは `pdftotext` でほぼ有用な文字が取れませんでした。
画像/スキャン寄りのPDFなので、現時点の根拠確認は XLSX、DOCX、目視、Geminiのmultimodal読取に寄ります。

PDF bbox と visual evidence review は改善対象です。
ただしMVPでは、bbox精度を値抽出評価のgateにはしません。

## Eval成果物

restricted fixture は次の構成です。

```text
visa-eval/test_cases_from_raw/<case_id>/<applicant_id>/
  scenario.json
  input/
    document_manifest.json
  expected/
    case_data.golden.json
    application_data.golden.json   # legacy/reference。MVPの正本ではない
    review.golden.json             # 残すがMVP gateではない
  generated/
    <run_id>/
      case_data.json
      field_metadata.json
      review.json
      comparison_report.md
```

MVPの正本はこれだけです。

```text
expected/case_data.golden.json
```

`application_data.golden.json` はMVP採点の正本にしません。
比較時に expected / generated の `case_data` から backend generator で rows を生成します。

```text
generated/case_data.json
expected/case_data.golden.json

expected case_data -> backend generator -> expected application_data rows
generated case_data -> backend generator -> generated application_data rows
```

## Golden status

全fixtureにまだ機械的なstatus fieldを入れなくても、運用上は次の状態で扱います。

| Status | 意味 | スコアの扱い |
|---|---|---|
| `partial` | scaffoldや既知の欠けが残る | モデル品質として使わない |
| `suspect` | 元資料との矛盾や未解決mismatchがある | 解消までスコアから外す |
| `reviewed` | 主要RASENS項目を元資料で確認済み | 暫定比較に使える |
| `locked` | 回帰確認用に固定したexpected | regression baselineに使える |

## 推奨フロー

```text
1. 小さいfixture setを選ぶ
   |
   v
2. document_manifest の use_as_input を確認する
   |
   v
3. raw資料を見て case_data.golden.json を補完・確認する
   |
   v
4. Gemini bytes eval を generated/<run_id> に出す
   |
   v
5. generated と expected を比較する
   |
   v
6. mismatch を分類する
      - Gemini の実ミス
      - golden の不足 / 誤り
      - 比較正規化不足
      - application_data / mapping / generator の差分
   |
   v
7. golden、比較ルール、prompt/schema のどれを直すか決める
   |
   v
8. 同じfixture setで再実行する
```

## Phase plan

### Phase 0: 評価境界を明確にする

- self-compare は smoke check と明記する。
- 実評価では必ず `generated/<run_id>` を `--generated` に指定する。
- Geminiやblind agentに `expected/` を渡さない。
- restricted fixture と generated output は git に入れない。

受け入れ条件:

- expected-vs-expected の100%を抽出精度として扱わない。
- モデル評価時は actual generated output を比較に使う。

### Phase 1: 2ケースの golden を補完する

最初の対象:

| Case | 理由 |
|---|---|
| `amit_tamang` | A社基本ケース |
| `kushang_subba_limbu` | 同じ会社資料で申請人差分を確認 |

`sanjay_gautam` は、manifest上の `submitted_application_pdf` が別人の申請書類束に見えるため、Phase 1 から外します。
家族・在日親族パターンは、正しい submitted application PDF が確認できたケースを後で追加します。

優先して確認する section:

- `applicant`
- `applicant.passport`
- `applicant.education`
- `applicant.family`
- `applicant.immigration_history`
- `entry_plan`
- `employer`
- `employment`

受け入れ条件:

- submitted application PDF を最終提出値の一次監査資料として確認する。
- XLSX、DOCX、会社書類は、その値がGemini入力資料から抽出可能だったかを判断するために使う。
- PDFにしかない値は、Gemini抽出ミスではなく固定値・手入力値・入力資料不足として分類する。
- `employment` と `employer` が意図せず欠けたままになっていない。
- 固定値・手入力値・抽出値が混ざっていない。
- fixtureに `partial` / `suspect` / `reviewed` / `locked` の扱いが付いている。
- `partial` / `suspect` の間は、スコアをモデル精度として引用しない。

### Phase 2: 比較ノイズを正規化する

小さく明示的に正規化します。

- yes/no/boolean
- 国名ラベル
- enumの大文字小文字
- `fill_value` が同等なRASENS表示ラベル
- 安全な日付・数値表記

受け入れ条件:

- `No`、`無`、`False` を boolean-like field では同値扱いできる。
- `NEPAL`、`Nepal`、`ネパール Nepal` を country-like field では同値扱いできる。
- `Married` と `Single` のような本当の差分は残る。

### Phase 3: 実Gemini evalを回してtriageする

実行例:

```bash
visa-app/backend/.venv/bin/python visa-eval/scripts/run_gemini_bytes_eval.py \
  <fixture_dir> \
  --output-dir <fixture_dir>/generated/<run_id>

visa-app/backend/.venv/bin/python visa-eval/scripts/compare_with_golden.py \
  --generated <fixture_dir>/generated/<run_id> \
  --expected <fixture_dir>/expected \
  --targets case_data,application_data
```

比較結果は次に分類します。

| Bucket | 意味 | 次の対応 |
|---|---|---|
| Gemini miss | モデルが違う値を出した | prompt/schema/scope改善 |
| Golden gap | expectedに有効な値がない | `case_data.golden.json` 更新 |
| Golden wrong | expectedが元資料と違う | golden修正 |
| Normalization noise | 意味は同じで表記だけ違う | 比較正規化を追加 |
| Mapping/generator issue | `case_data` は正しいがrowsが違う | backend generator / mapping修正 |

受け入れ条件:

- reportが単なる割合ではなく、作業キューとして読める。
- 各mismatchに原因カテゴリが付く。

### Phase 4: 初期ケースが安定した後に広げる

最初の2ケースが `reviewed` 相当になってから広げます。

- `single_smoke` 13ケースへ拡張
- 正しい submitted application PDF がある家族・在日親族パターンを追加
- `field_metadata` / source evidence review を追加
- XLSX cell、DOCX block anchorの確認を追加
- PDF bboxのレビュー観点を追加

厳密な bbox IoU 採点はまだ入れません。
MVPでは bbox は人間レビュー補助であり、抽出値の主スコアではありません。

## まだやらないこと

- `application_data.golden.json` を正本にする。
- `review.golden.json` を gate として採点する。
- source_ref / PDF bbox が安定する前に bbox IoU を採点する。
- golden completeness と比較正規化の状態を説明せずに単一スコアを出す。
- restricted raw、generated、expected golden を git に入れる。
- Chrome拡張QA、frontend review QA、抽出evalを1つのスコアに混ぜる。
- 最初の2ケースが意味ある状態になる前に、fixture数だけ増やす。

## 関連リンク

- Fixture contract: `../../../visa-eval/docs/fixture_contract.md`
- Eval workspace guide: `../../../visa-eval/AGENTS.md`
- Current eval workspace README: `../../../visa-eval/README.md`
- Source-ref and bbox roadmap: `../007_source_refs_schema_migration/README.md`
- Canonical case data: `../002_review_field_order/canonical_case_data_v2.md`
