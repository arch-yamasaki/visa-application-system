# AI抽出の正解検証方針

- 作成日: 2026-08-31
- 状態: 方針 + 初期実装済み
- スコープ: AI抽出結果、golden、RASENS変換値の検証

## 1. 結論

今回の検証は、次の2本に分ければよい。

1. **AI抽出の検証**

   AIが出した `case_data` と、人が確認した `case_data.golden.json` を比較する。

2. **RASENS変換の検証**

   正しい `case_data` を変換した結果が、期待するRASENS入力値になるかを確認する。

```text
原資料
  |
  v
AI抽出結果 --------比較-------- golden case_data
  |                                  |
  v                                  v
RASENS変換結果                  期待するRASENS入力値
  |                                  |
  +---------------比較---------------+
```

OCR、AI抽出、RASENS変換、ブラウザ入力を一つの点数に混ぜないことが最も重要である。

## 2. データを6種類に分ける

| データ | 意味 | 検証での扱い |
|---|---|---|
| 原資料 | PDF、画像、XLSX、DOCX | 人が正解を確認する根拠 |
| OCR・前処理結果 | OCR文字列、XLSXセル文字列など | 読み取り失敗を調べる補助データ |
| AI抽出結果 | 1回のAI実行が出した `case_data` | **AI抽出の比較対象** |
| golden | input資料・申請済み値・業務規則を人が照合して確定した `case_data` | **評価上の正解** |
| 本番の現在値 | AI結果と人の修正を反映した現在の `case_data` | 業務用。AI単体の採点には使わない |
| `application_data` | `case_data` をRASENS入力用に変換したrows | **変換・入力確認の対象** |

本番アプリの現在の `case_data` は、AI結果、人の修正、過去の値が混ざる可能性がある。したがって、AI単体の精度を測るときは使わず、1回のAI実行が出した未mergeの結果を使う。

## 3. goldenをどう作るか

### goldenはPDFの単純な転記ではない

今回のPDFには、性質の異なる情報がある。

| 資料 | 分かること | AIへ渡すか |
|---|---|---:|
| `input/` の旅券、証明書、雇用条件書など | 原資料に書かれた事実 | 渡す |
| `output/rasens_application/` の入力済み申請書 | 実際の申請で採用・入力された値 | 渡さない |

入力済み申請書PDFは、最終的に何を入力したかを知る重要な監査資料である。ただし、入力された値が原資料と違っている可能性もあるため、PDFの値を無条件に正解へコピーしない。

goldenは、次の3つを人が突き合わせて確定する。

```text
AIへ渡したinput資料の事実
        +
入力済み申請書PDFで採用された値
        +
アプリの固定値・変換規則・人の判断
        |
        v
人が確認したcase_data.golden.json
```

したがって、`case_data.golden.json` は「原資料の全文転記」でも「入力済み申請書PDFの丸写し」でもない。アプリが最終的に持つべき、canonical形式の期待値である。

### 必要な中間情報

値のgoldenを2つ作ると、同じ値の二重管理になる。代わりに、既に予定している `golden_manifest.json` へ、fieldごとの役割だけを追加する。

```json
{
  "revision_id": "v0001",
  "status": "reviewed",
  "field_rules": {
    "applicant.name_roman": {
      "scope": "extraction",
      "basis": "input_document",
      "verification": "verified"
    },
    "entry_plan.main_activity_category": {
      "scope": "application_only",
      "basis": "fixed_policy",
      "verification": "verified",
      "reason_code": "application_or_policy_field"
    },
    "employment.activity_details": {
      "scope": "application_only",
      "basis": "human_decision",
      "verification": "verified",
      "reason_code": "application_wording_or_human_review"
    }
  }
}
```

`scope` は3種類だけにする。

| scope | 意味 | AI抽出スコア |
|---|---|---:|
| `extraction` | AI入力資料から取れるべき値 | 含める |
| `application_only` | 固定値、手入力、人の判断、申請時の補完値 | 含めない |
| `excluded` | input/output矛盾、未確認、評価対象外 | 含めない |

`basis` は、必要な範囲で次を使う。

- `input_document`: AIへ渡した原資料で確認
- `input_and_application`: 原資料と入力済み申請書の両方で一致
- `application_output`: 入力済み申請書でのみ確認
- `fixed_policy`: アプリ・業務の固定値
- `derived`: 他の値や規則から導出
- `human_decision`: 人が申請向けに判断・作成

未分類fieldはAI採点へ含めない。誤って `application_only` の値をAIのmissingにするより、安全側に倒す。goldenを `reviewed` または `locked` にする前に、比較対象の非空fieldをすべて分類する。

運用を重くしないため、最初にgoldenの非空fieldを自動列挙して `unclassified` の下書きを作り、人は分類と例外だけを確認する。値そのものはmanifestへ複製しない。

### input資料と申請PDFを照合するルール

| input資料 | 入力済み申請書PDF | 扱い |
|---|---|---|
| 同じ意味の値がある | 同じ意味の値がある | `extraction`。表記差は比較時に正規化 |
| 値がある | 空欄 | 原則 `extraction`。その申請で不要なら理由を付けて除外 |
| 値がない | 値がある | `application_only`。AIのmissingにしない |
| 値が違う | 意図した変換・人の判断で説明できる | `application_only` と理由を記録 |
| 値が違う | 理由を説明できない | `excluded` / `conflict`。解消までgoldenをlockしない |

重要なのは、入力済み申請書PDFを「実際に入力した値の証拠」として使い、「必ず正しい値の証拠」とは決めつけないことである。

### 比較時の使い分け

```text
AI抽出評価:
  AI case_data
  vs
  case_data.golden.json のうち scope=extraction かつ verified の項目

申請値・RASENS確認:
  case_data.golden.json 全体
  -> application_data
  -> 入力済み申請書PDFまたは独立expected rowsと確認
```

これにより、goldenの値正本は1つのまま、AIが読むべき値と、アプリ・人が補う値を混同せずに済む。

## 4. どことどこを比較するか

### A. AI抽出の主比較

```text
AI実行結果/case_data.json
        vs
expected_verified/case_data.golden.json のうち
scope=extraction かつ verification=verified の項目
```

これで答える問い:

> AIは、入力資料から必要な案件情報を正しく構造化できたか。

ここで比較するのは値だけである。

- 氏名
- 生年月日
- 国籍
- 旅券情報
- 学歴、職歴
- 雇用条件
- 会社情報
- 活動内容など

人が修正した後の本番 `case_data` や、RASENS変換後の値を混ぜない。

### B. 根拠情報の確認

```text
AI実行結果/field_metadata.json
        vs
原資料の該当ページ・引用箇所
```

これで答える問い:

> その値を、正しい書類の正しい箇所から取得したか。

値の正誤とは別に確認する。

- `document_id` は存在するか
- ページ番号は正しいか
- quoteが原資料に存在するか
- 値があるのに根拠が空ではないか
- bboxやanchorで該当箇所を表示できるか

初期MVPでは、値の比較を主gateにする。bboxの厳密な座標スコアは後回しでよい。

### C. RASENS変換の主比較

```text
正しい合成case_data
  -> mapping/generator
  -> 実際のapplication rows

期待するapplication rows
  -> 人がRASENS仕様・実画面から作成

両者を比較
```

これで答える問い:

> `case_data` が正しいとき、RASENSへ正しい形式で変換できるか。

対象例:

- 日付が `YYYYMMDD` になるか
- booleanやenumが正しい選択肢になるか
- 金額、電話番号の形式が正しいか
- 配列がRASENSの繰返し欄へ正しく割り当たるか
- 表示条件に合わないrowを入れていないか
- 組織設定や固定値が正しく入るか

期待値は同じgeneratorで自動生成しない。同じgeneratorで両側を作ると、mappingが間違っていても両方が同じ間違いになり、テストを通るためである。

### D. End-to-endの補助比較

```text
AI case_data -> application rows
golden case_data -> application rows
```

これは次を見る補助比較である。

> AIの抽出ミスが、最終的なRASENS入力へどの程度影響するか。

両側を同じgeneratorで変換するため、mapping自体が正しいことの証明には使わない。

### E. Chrome拡張の入力確認

```text
application rows
        vs
入力後にDOMから読み返した値
```

これで答える問い:

> Chrome拡張は、指定されたRASENS項目へ実際に正しい値を入れたか。

これはAI抽出評価とは別のQAである。初期の検証整備が終わってから追加してよい。

## 5. OCR結果はどう扱うか

OCR結果を全ケースの主正解データにはしない。

理由:

- PDFをGeminiへ直接渡す経路では、独立したOCR文字列が作られないことがある。
- XLSX、DOCX、画像、PDFで前処理方法が異なる。
- 最終的に必要なのは、全文OCRの完全一致ではなく、必要な申請項目を正しく抽出できることである。

したがって、通常は次の順で調べる。

1. AI `case_data` とgoldenが一致しているか確認する。
2. 不一致があった項目だけ `field_metadata` と原資料を見る。
3. 原資料の文字をAIが読めていなければ、その時点でOCR・前処理結果を調べる。

OCR評価を独立して行いたい書類が出た場合だけ、対象ページと項目を限定したOCR fixtureを作る。全資料の全文正解OCRは作らない。

## 6. `canonical` はどう考えるか

`canonical` は別データの名前ではなく、`case_data` の形式を表す言葉として使う。

```text
canonical case_data
= 決められたpath、型、enum、単位に揃えたcase_data
```

必要なのは `case_data` 1つであり、同じ現在値を `canonical_case_data` という別ファイル・別正本で持つ必要はない。

ただし、次は分ける。

- AIが出した未確認の `case_data`
- 人が確認したgolden `case_data`
- 本番アプリで現在使っている `case_data`
- `case_data` から生成した `application_data`

JSONの形が似ていても、目的が異なるためである。

## 7. goldenと旧版のファイル構成

旧goldenは**不変データ**として扱う。値の補正、schema変換、整形、field分類の追記は行わず、元のJSONをbyte単位でそのまま残す。

今回の実データでは、既存の `expected/` を旧データとして固定し、新しい検証用データを `expected_verified/` に横並びで作る。これが一番単純で、旧データを変更したかどうかも `cmp` とchecksumで確認しやすい。

```text
visa-eval/test_cases_from_raw/<case_id>/<applicant_id>/
  input/
    document_manifest.json
    files/

  output/
    output_manifest.json
    rasens_application/

  expected/
    case_data.golden.json       # 旧データ。今回は変更しない

  expected_verified/
    case_data.golden.json       # 新データの値正本。旧値から始め、必要な修正はここだけに入れる
    golden_manifest.json        # fieldごとの役割、確認状態、旧golden checksum
```

ルール:

- 旧 `expected/case_data.golden.json` は編集しない。
- 新しい比較では `--expected .../expected_verified` を明示する。
- `expected_verified/case_data.golden.json` は値の正本、`golden_manifest.json` は採点対象を決める補助情報にする。値をmanifestへ複製しない。
- `golden_manifest.json` に旧goldenのchecksumを入れる。
- fieldは `extraction`、`application_only`、`excluded` の3つだけに分類する。
- AI抽出スコアは `scope=extraction` かつ `verification=verified` だけを母数にする。
- 未確認fieldは `needs_review` のまま残し、AIのmissingやmismatchに混ぜない。
- 未確認fieldが残る間はmanifestの状態を `partial` とし、比較値をモデル全体の精度とは呼ばない。
- 将来 `expected_verified/case_data.golden.json` の値を直す場合も、旧 `expected/` ではなく `expected_verified/` 側だけを更新する。

これで、旧データ保存と新データ検証を同じ仕組みに押し込まずに済む。

## 8. AI実行結果のファイル構成

1回のAI実行結果は、他のrunや本番の現在値と混ぜない。

```text
visa-eval/eval_runs/<run_id>/<case_id>/
  case_data.json
  field_metadata.json
  review.json
  run_manifest.json
  comparison_case_data.md
  comparison_application_impact.md
```

`run_manifest.json` に最低限残すもの:

- run id
- 実行日時
- 使用model
- thinking / retry設定
- コードcommitとdirty状態
- prompt / schemaのhash
- scenario / input manifestのhash
- 入力document数とbytes合計

PII値、実ケース識別子、実ファイル名は入れない。golden revisionは抽出runではなく、goldenと照合した比較結果側へ記録する。既存runには `run_manifest.json` がないものがあるため、実行条件の完全な再現性には制約がある。今後のrunでは上記manifestを必須にして、この制約を明示的に減らす。

モデルの生レスポンス全文やOCR全文を、通常runで無期限に複製する必要はない。

## 9. mismatchの分類

比較結果は、次の作業分類を付ける。

| 分類 | 意味 | 対応 |
|---|---|---|
| AI miss | AIの値が原資料・goldenと違う | prompt、schema、抽出処理を改善 |
| Missing | goldenにある値をAIが出していない | 入力資料、prompt、scopeを確認 |
| Extra | AIにはあるがgoldenにない | golden不足か過剰抽出かを人が確認 |
| Golden gap | goldenに必要な値が未記入 | goldenを監査して更新 |
| Golden wrong | goldenが原資料と違う | 旧版を残してgoldenを修正 |
| Input/output conflict | 原資料と入力済み申請書の値が違い、理由が未確認 | 解消まで採点対象外にし、goldenをlockしない |
| Normalization noise | 意味は同じで表記だけ違う | path限定の比較正規化を追加 |
| Evidence issue | 値は合うが根拠がない・違う | source ref、anchor処理を改善 |
| Mapping issue | case_dataは正しいがRASENS値が違う | mapping/generatorを修正 |
| Browser fill issue | rowsは正しいがDOM入力が違う | selector、入力処理を修正 |

この分類を付けず、すべてをAIの誤りとして数えない。

## 10. 指標

最初は次だけで十分である。

- golden比較対象項目数
- match数
- mismatch数
- missing数
- extra数
- 値あり・根拠なしの項目数
- 人手確認後の原因分類件数

また、goldenの確認状態を必ず表示する。

| 状態 | 意味 | スコアの扱い |
|---|---|---|
| `partial` | まだ不足がある | モデル精度と呼ばない |
| `reviewed` | 原資料と照合済み | 暫定評価に使える |
| `locked` | 変更理由と確認者を記録済み | 回帰テストの基準に使える |

`partial` のgoldenとの一致率は「機械比較一致率」と呼ぶ。

### 指標を分ける

2026-09-02時点では、値精度、根拠、画面表示を同じ数字へ混ぜない。

| 指標 | 見るもの | 扱い |
|---|---|---|
| 値精度 | AI `case_data` と verified extraction のgolden値 | 主スコア |
| source_ref充足 | `field_metadata.source_refs[]`、quote、input manifest内document id | 根拠が追えるかの補助指標 |
| anchor表示 | PDF bbox / XLSX cell / DOCX block がviewerで表示可能か | UI確認指標 |
| semantic正確性 | 表示された位置が意味上も正しい根拠か | 人手レビュー指標 |
| extra | AIにだけ非空値があるpath | 分母外。golden候補か抽出抑制対象かを別判断 |

`source_ref` が存在することは、anchorが画面表示できることや、semanticに正しい位置であることを保証しない。統一アンカー方針では、`source_ref` は出典、`source_locations` は表示位置、`anchor` はviewer用の位置情報として別々に扱う。

## 11. 検証の実行手順

### 1. goldenを確認する

- input資料と、golden作成用のoutput資料を人が確認する。
- AI入力資料に存在しない値を、AIの抽出正解として要求しない。
- 各非空fieldを `extraction`、`application_only`、`excluded` のいずれかに分類する。
- input/outputの説明できない矛盾があれば `excluded` にし、解消までlockしない。
- golden状態を `partial`、`reviewed`、`locked` のどれかにする。

### 2. AIをブラインド実行する

- AIへ `expected/` を見せない。
- run専用directoryで実行する。
- AI出力を `case_data.json`、`field_metadata.json`、`review.json` に分ける。

### 3. `case_data` を比較する

- AI runの `case_data.json` と `expected_verified/case_data.golden.json` のうち、`scope=extraction` かつ `verification=verified` のfieldだけを比較する。
- mismatch、missing、extraを出す。
- `application_only`、`excluded`、未分類の件数も別に表示し、採点へ混ぜない。
- 表記揺れはpath限定の正規化だけを適用する。

### 用語: scoring scope と extraction scope

この文書で `golden_manifest.json` に記録する `scope` は、採点対象を決める **golden scoring scope** である。

| scoring scope | 意味 |
|---|---|
| `extraction` | AI入力資料から取れるべきverified値。値精度の母数に入れる |
| `application_only` | 固定値、申請時補完、人判断、RASENS側だけで決まる値。母数に入れない |
| `excluded` | input/output矛盾、未確認、評価対象外。母数に入れない |

一方、Geminiを `identity`、`employer`、`education`、`review` などに分けて実行する単位は **Gemini extraction scope** である。これは処理・schema・promptの分割単位であり、golden scoring scopeとは別物である。既存JSONキーの大移行は避け、docs上で呼び分ける。

### 4. 人が原因分類する

- AI miss
- golden gap/wrong
- normalization noise
- evidence issue

### 5. 必要な層だけ直して再実行する

- 抽出問題ならAI側を修正する。
- golden問題なら旧 `expected/` は触らず、`expected_verified/` 側だけを修正する。
- mapping問題なら合成mapping testを修正・追加する。
- 各変更後、同じfixtureで回帰確認する。

## 12. 作業計画

### Phase 1: verified goldenを旧データと分ける

- `golden_manifest.json` の契約を追加する。
- `golden_manifest.json` にfieldごとの `scope`、`basis`、`verification` を追加する。
- 既存の旧golden・旧fixtureは変更しない。
- `expected_verified/` に新しい値正本とsidecar manifestを作る。
- `expected_verified/` の非空fieldをmanifest側で分類し、未確認は採点対象外にする。

完了条件:

- 旧golden本体が変更前とbyte単位で同じことをchecksumで確認できる。
- golden値を変えた場合も、旧 `expected/` と新 `expected_verified/` を区別して戻せる。
- 比較器は指定された `--expected` ディレクトリだけを読む。
- blind runにexpectedが漏れない。

### Phase 2: AI抽出比較を明確にする

- 各runに `run_manifest.json` を追加する。
- AIの未merge `case_data.json` を比較対象に固定する。
- 比較器で `golden_manifest.json` を読み、verifiedな `extraction` fieldだけを採点する。
- レポートにmatch、mismatch、missing、extra、採点対象外・未分類件数と原因分類を出す。

完了条件:

- 本番の現在値や人の修正を混ぜずにAI単体を評価できる。
- 固定値や人の判断値をAIのmissingとして数えない。
- 使用model、prompt、golden revisionを後から確認できる。

### Phase 3: mappingを独立検証する

- PIIなしの小さな合成 `case_data` fixtureを作る。
- RASENS仕様・実画面から、人が `expected_rows` を確認する。
- 日付、enum、金額、繰返し、条件表示を個別にテストする。
- 実際に読み込んだmapping version/hashを記録する。

完了条件:

- mappingを意図的に壊すとテストが失敗する。
- AIの抽出ミスとmappingのミスを別々に判断できる。

### Phase 4: 必要になったらブラウザ入力を検証する

- 入力後のDOM値をreadbackする。
- rowsとreadbackを比較する。
- AI抽出スコアとは別のChrome拡張QAとして扱う。

Phase 1〜3が整うまでは後回しでよい。

## 13. 今回は考えないこと

本書は正解データと比較方法だけを扱う。本番の保存基盤、復元UI、法務・PII運用などは、検証方法が固まった後に別文書で扱う。

## 14. まず実施する順番

```text
1. input資料と入力済み申請書PDFを照合する
2. goldenの各fieldをextraction / application_only / excludedに分類する
3. golden値を直す場合は旧 `expected/` ではなく `expected_verified/` 側だけを変更する
4. AI runの未merge case_dataをverifiedなextraction fieldだけと比較する
5. mismatchを原因分類する
6. 合成fixtureでRASENS mappingを独立テストする
7. 必要になったらChrome拡張のDOM readbackを追加する
```

この順なら、保存基盤や運用制度の議論を先に広げず、まず「何が正しく、どこで間違ったか」を判別できる。

## 15. 2026-08-31 初期実装時点

このセクションは初期実装時点の記録である。最新の監査結果は後続の「2026-09-01 追加監査結果」を参照する。

今回の初期実装では、旧 `expected/case_data.golden.json` は変更しない。新しく作ったのは `expected_verified/` 側のデータ一式である。

```text
expected/
  case_data.golden.json      # 旧データ。byte単位で変更しない

expected_verified/
  case_data.golden.json      # 新データの値正本。初期状態では旧値と同一
  golden_manifest.json       # fieldごとの採点スコープ、根拠種別、確認状態
```

比較サマリは `expected_verified/` に置かず、各run側の `comparison_verified.json` に保存する。`expected_verified/` は値正本とmanifestの2ファイルだけに保つ。

active 2 fixtureに `expected_verified/` を追加した。fixture名はrestricted情報なので、ここでは匿名ラベルだけにする。

| fixture | field_rules | extraction | application_only | excluded | needs_review | scored |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 65 | 41 | 20 | 4 | 33 | 14 |
| 2 | 74 | 42 | 23 | 9 | 39 | 14 |

`compare_with_golden.py` は、manifestがある場合だけ `scope=extraction` かつ `verification=verified` のfieldを採点する。manifestがなければ従来通り全field比較になる。manifestにgoldenへ存在しないpathがあれば、採点母数へは入れず、manifest pathエラーとしてNGにする。

分類方針は、まずシンプルに次で固定した。

| scope | 今回入れた主なfield |
|---|---|
| `extraction` | 本人基本情報、旅券、学歴、職歴、入国/申請歴、雇用条件、会社情報 |
| `application_only` | 日本連絡先、代理人、entry plan、活動内容文章など申請用補完・人判断・導出値 |
| `excluded` | 自動照合だけでは根拠を十分に確認できない値 |

fresh run `20260831_verified_golden_check` をmanifest scopedで確認した結果:

- 比較モードはすべて `manifest_scoped`
- manifest pathエラーは0件
- unclassifiedは0件
- 採点母数は各fixture 14項目
- fixture 1は12 match、1 mismatch、1 missing（85.7%）
- fixture 2は11 match、2 mismatch、1 missing（78.6%）
- golden外のAI出力は各fixture 5項目。正答率の母数には入れず、過剰抽出またはgolden不足の確認対象として表示
- 比較サマリはrun側の `comparison_verified.json` にだけ保存
- 旧goldenと新 `expected_verified/case_data.golden.json` は `cmp` で一致
- 旧goldenのsha256はmanifestに保存済み

不一致を項目単位で確認すると、職業と役職有無の値違い、職歴の国区分のmissingが残った。golden外の5項目には、根拠anchorが解決している新schema fieldも含まれるため、AIの誤りと決めつけずgolden不足候補として扱う。

fresh runの根拠情報も別に監査した。全source refの `document_id` はinput manifest内にあり、空quoteは0件だった。採点対象28項目中25項目にsource refがあり、その25項目はanchor情報も持っていた。値比較とは別に、anchorの品質はevidence reviewとして扱う。

これで、代理人情報・申請側で決める値・人が確定する文章を、AIの抽出漏れとして誤計上しない形になった。ただしこの時点のmanifestはまだ `partial` であり、今回の85.7% / 78.6%は確認済み項目だけの一致率である。

注意点:

- RASENS出力PDFは画像PDFだったため、`pdftotext` では値を読めなかった。OCRを使って補助照合したが、OCR結果そのものは保存していない。
- この時点の `needs_review` は不備ではなく、まだ人が確認していないのでAI採点に入れないという状態である。
- この時点では新 `case_data.golden.json` の値は旧goldenと同一にした。値の修正が必要なfieldは、次の人手確認で `expected_verified/` 側だけを直す。
- 追加の限定監査で、雇用履歴有無、月不明flag、経験月数は派生値として `application_only/derived` に移した。退去強制歴とIT資格有無の否定booleanはfresh runにsource_refsがなかったため、`extraction/needs_review` に落とした。職業と職歴の国区分はinput資料で明示値が確認できたため、`extraction/verified` のまま維持した。

## 17. 2026-09-01 追加監査結果

目的は、active fixtureの採点母数を増やし、`needs_review` を残しすぎないこと。今回は旧 `expected/` は一切変更せず、`expected_verified/` だけを監査・更新した。

実施した確認:

- Excel intake sheet: 本人基本情報、旅券番号、入国歴、COE申請歴、犯罪歴、家族有無、最終学歴を確認
- 添付PDF: 旅券、卒業証明、成績証明、源泉徴収票等をページ画像で確認
- 雇用条件DOCX: 月給、契約種別、期間、職務内容の元情報を確認
- 会社PDF: 登記事項、会社概要、決算書をページ画像で確認
- RASENS出力PDF: application_onlyの監査資料として確認

更新結果:

| fixture | field_rules | extraction | application_only | excluded | needs_review | scored |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 65 | 37 | 23 | 5 | 0 | 37 |
| 2 | 74 | 37 | 28 | 9 | 0 | 37 |

主な判断:

- `needs_review` はactive 2件とも0にした。
- AI入力資料から直接またはアプリ向け正規化で確認できる値は `extraction/verified` にした。
- RASENS出力PDFにしかない値、代理人、固定値、人が申請用に作る文章は `application_only/verified` にした。
- 否定値や回数など、AI抽出精度として数えると不安定な派生・補助項目は `excluded/verified` にした。
- 会社の従業員数は旧golden値ではなく、会社概要PDFの明示値に合わせて、両fixtureの `expected_verified/case_data.golden.json` 側だけ修正した。
- 独立監査で判断が分かれた `employer.office_name` は、入力資料から抽出する会社名ではなく申請側の事業所名ラベルなので、`application_only/verified` に確定した。

fresh run `20260831_verified_golden_check` を再比較した結果:

| fixture | scored | match | mismatch | missing | accuracy |
|---:|---:|---:|---:|---:|---:|
| 1 | 37 | 30 | 7 | 0 | 81.1% |
| 2 | 37 | 28 | 9 | 0 | 75.7% |
| **合計** | **74** | **58** | **16** | **0** | **78.4%** |

不一致16項目は、goldenの未確認ではなく、AI出力側の値変換・選択の問題として扱う。両fixtureに共通する主な対象は、出生地、住所、性別、職業、会社住所、法人番号、職種カテゴリである。fixture 2では、これに学歴区分と役職有無が加わる。

AIの根拠参照も別に確認した。採点対象74項目中73項目に `source_refs` があり、全refの `document_id` はinput manifest内、空の `text_quote` は0、anchorなしも0だった。fixture 1の `applicant.occupation` だけrefがなく、値比較でも不一致なので、AI側の根拠不足として残す。source refの有無はgolden正しさの代用にはせず、原資料監査とは別の品質指標にする。

application_data比較も実行したが、これは主スコアではない。同じgeneratorを通すため、AI抽出ミスがRASENS投入値にどう波及するかを見る補助指標として扱う。

今回の状態:

- manifest status: `reviewed`
- manifest path error: 0
- unclassified: 0
- needs_review: 0
- 旧golden checksum: manifest記録と一致
- 旧goldenと新goldenの値差分: 両fixtureとも `employer.employee_count` の1pathだけ
- Claude Code: ログイン確認はできたが、セッション上限でsubagentレビュー結果は取得できなかった

この78.4%は、2案件に含まれる検証済み抽出74項目のfield-level一致率である。初期の28項目より母数は増えたが、case-levelの母数は2件のままなので、技人国案件全体へ一般化できる精度ではない。次に精度の信頼性を上げるには、同じ74項目を細分化するのではなく、原資料付きfixtureそのものを追加する。

## 18. 2026-09-01 fixture追加

原資料の結合PDFをoutput/inputへ物理分割し、fixtureを2名から8名へ増やした。この時点では追加6名はGemini dry-runまで実行可能で、`expected_verified` は未作成だった。

当時の数え方:

- fixture ready: 8名
- scoring ready: 2名
- golden pending: 6名

追加内容とPDF境界は `visa-eval/docs/dataset_expansion_20260901.md` に記録する。その後、次節の作業で新規6名の `expected_verified` を作成し、全8名を scoring ready にした。

## 19. 2026-09-01 8 fixture scoring ready

追加6 fixtureにも `expected_verified/case_data.golden.json` と `golden_manifest.json` を作成し、全8名を scoring ready にした。新規6名には旧 `expected/case_data.golden.json` がないため、旧データは作らず、`source_expected_dir` と `source_golden_sha256` は `null` にしている。

Codex実装担当3名が2 fixtureずつ作成し、担当を入れ替えた3名で交差レビューした。Claude Code側の複数役レビューも参考にしたが、最終判断はCodex側で原PDF、同一資料SHA、manifest coverage、独立再抽出runを再確認して確定した。

今回も正解値は「PDF文字列の丸写し」ではなく、アプリ内部で持つ canonical `case_data` の期待値として作った。RASENS出力PDFにだけ出る固定値・代理人・日本連絡先・申請文言・人判断値は `application_only`、input/outputで意味が衝突する値や空欄補助値は `excluded` とし、AI抽出の分母へ混ぜない。

最終状態:

| 対象 | field_rules | extraction | application_only | excluded | needs_review |
|---|---:|---:|---:|---:|---:|
| 既存2名 | 139 | 74 | 51 | 14 | 0 |
| 新規6名 | 442 | 241 | 143 | 58 | 0 |
| 合計8名 | 581 | 315 | 194 | 72 | 0 |

検証:

- 全8件の manifest status は `reviewed`
- `needs_review`: 0
- `unclassified`: 0
- manifest path error: 0
- `check_compare_with_golden.py`: pass
- `20260901_eight_fixture_rescore` の当時の採点対象321項目では、match 255、mismatch 66、missing 0、extra 44

この 255/321 = 79.4% は当時の確認済み extraction field に限った履歴値である。現在は、input原資料で年月までしか確認できない入社日6項目を `application_only` へ移したため、採点対象は315項目である。RASENS変換、Chrome入力、Firestore保存などの評価は含めない。

交差レビューでは、同じSHA-256の会社資料を使う7 fixtureで会社情報が揺れていることを検出した。既存の原資料監査済みfixtureを基準に会社情報13項目とscopeを統一し、AI下書き由来の桁落ち・欠落・補助欄への誤配置を修正した。また、input CVとRASENS outputで職歴の行構成が衝突する1 fixtureは、値を残したまま職歴9項目を `excluded` にした。独立再抽出runのsource refsは321項目中316項目（98.4%）に存在し、参照document idのmanifest外参照と空quoteは0だった。

8件目では、学歴の学校名粒度と卒業日の扱いで input と RASENS output に差があった。学校名は既存fixtureと同じ大学名粒度へ寄せ、抽出採点ではなく `application_only` にした。卒業日は final app value を保持しつつ、input/output conflict として `excluded` にした。

## 20. 2026-09-02 検証修正と8 fixture再評価

比較器の限定正規化、内部値契約、現行RASENS職種ラベル、入社日のscope、Gemini一時障害retryを修正し、別担当レビュー後に8 fixtureを再実行した。

住所・法人番号・役職のgolden再監査前の履歴結果:

| 指標 | 件数 |
|---|---:|
| 採点対象 | 315 |
| 一致 | 259 |
| 不一致 | 56 |
| 抽出漏れ | 0 |
| extra | 34 |
| scope失敗 | 0 |

AI抽出のgolden比較一致率は 259/315 = 82.2%。一致259項目は全件にsource refsとquoteがあり、参照document idもinput manifest内だった。golden側は `needs_review=0`、`unclassified=0`、manifest path error 0を維持している。この数値は次節の再監査により更新済みである。

主な不一致は住所系19、法人番号系10、役職系10。extra 34は職歴配列差19、会社郵便番号7、日本連絡先5、役職名3で、全件に原資料引用がある。extraは正答率の分母へ入れず、golden候補か抽出抑制対象かを別に判断する。

詳細は `visa-eval/docs/accuracy_report_20260902.md` を参照する。

## 21. 2026-09-02 住所・法人番号・役職のgolden再監査

39 field mismatchを画像証拠付きで再監査した。判定基準は次の1つだけとする。

> AIに渡したinput資料だけで、値と粒度を一意に決められるか。

確定したルール:

- 出生地と本国住所は、対応するinput資料の値を `extraction` とする。別種類の住所は転用しない。
- 所属機関住所は、RASENSにだけある建物名等の粒度までinputから決められない場合、値を残して `application_only` とする。
- 法人番号は、inputに「法人番号」として明示された13桁だけを `extraction` とする。12桁の会社法人等番号や、ラベルのない13桁は採用しない。
- `has_corporate_number` は番号本体から、`has_position` は役職名から決まる派生booleanとし、`application_only / derived` で二重採点しない。
- `position_title` は組織上の正式な地位・役職名だけとする。Offer Letterの `Position` 欄でも、値が職種・担当業務なら役職にしない。

再監査後の契約は、8 fixture、577 field rules、287 verified extraction値項目、218 application_only、72 excluded、needs_review 0、unclassified 0、manifest path error 0。同じAI runの再採点は260/287 = 90.6%だが、これはモデル改善ではなく評価データ修正の影響である。以前の 259/315 = 82.2% は、golden再監査前の履歴値として扱う。

旧 `expected/` が存在する2 fixtureはSHA不変。新規6 fixtureには旧goldenが元からないため、後から旧版を作らない。

## 22. 関連資料

- `visa-eval/docs/fixture_contract.md`
- `visa-eval/docs/accuracy_report_20260902.md`
- `visa-app/docs/008_eval_workflow/README.md`
- `docs/shared/013_ocr_document_parsing/README.md`
- `docs/shared/015_extraction_pipeline_flow/README.md`
- `rasens-autofill/docs/データ設計.md`
