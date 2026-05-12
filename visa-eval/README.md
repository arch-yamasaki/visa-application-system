# visa-eval

このディレクトリは、Codex やAIエージェントに実PDF・Excelを読ませて、在留資格申請データの抽出・正規化・申請入力生成を検証するためのローカル restricted evaluation workspace です。

初期は `expected/*.golden.json` のたたき台をCodexで作り、人手確認後にgolden化する。評価時は、AI出力の `generated/*.json` を人手確認済みの `expected/*.golden.json` と比較する。

## 重要: 制限付きデータ

`raw/申請書類` には実案件由来の個人情報を含む原資料があります。これは匿名化済みfixtureではありません。

このディレクトリでは、実データ利用を許可します。ただし、`raw/`、`catalog.json`、`fixtures_single/**`、`generated/**`、レビュー用キャプチャ、DevTools出力はすべて `restricted test data` として扱います。

- 外部共有しない。
- スクリーンショット、ログ、Console出力、Network exportに含めない。
- bug reportやチャットへ貼り付ける場合は、氏名、住所、電話、メール、旅券番号、申請番号、自由記述を伏せる。
- 実案件rawから作った `generated/` も個人情報を含みうるため、rawと同じ制限付きデータとして扱う。
- 長期的には、リポジトリ内に置くのは匿名化済みfixtureだけにし、実rawはリポジトリ外の制限領域へ移す。

## Git管理

この配下の実データ本体は git 管理しない。

- 管理する: `README.md`, `eval/suites/*.json`, `fixtures_single/README.md`
- 管理しない: `raw/`, `catalog.json`, `fixtures_single/<case_id>/`, `generated/`

`catalog.json` や `fixtures_single/*/*/expected/*.golden.json` はJSONでも実PIIを含むため、ソースコードや設計資産とは分けて扱う。

## リスクと対策

| リスク | 何が起きるか | 対策 |
| --- | --- | --- |
| ローカルファイル残存 | `raw/申請書類.zip` や展開後PDF、途中出力JSON、比較用スクリーンショットが端末に残り、別用途の検索やバックアップから見つかる。 | 置き場所をこのディレクトリ配下に限定する。検証後は不要なZIP、複製、スクリーンショットを削除する。 |
| `chrome.storage.local` 残存 | このディレクトリのfixtureから生成した投入データがChrome側に残り、別ケース確認時に混線する。 | 実データケースの確認は専用Chromeプロファイルで行い、ケース切替時と終了時に `chrome.storage.local` を削除する。 |
| DevTools console / screenshot / generated JSON 残存 | `fixtures_single/<case_id>/<applicant_id>/generated/` やDevTools出力に氏名、住所、学歴、雇用条件、自由記述が残り、再利用時に漏えいする。 | `generated/` は期待値比較に必要な最小限だけ保持する。Console実値ログを避け、スクリーンショットや生成JSONを共有する場合はマスク版を使う。 |
| Git / 共有フォルダ混入 | 実PIIを含むrawやgeneratedを誤ってcommit/pushしたり共有ドライブへ同期したりすると、履歴と複製先に残る。 | 実PII入りファイルは原則Git・共有同期対象にしない。公開用fixtureは匿名化済みまたは合成データのみとする。 |
| bug報告 / チャット転記漏えい | 再現説明のため `generated/application_data.json` やConsole断片を貼り、そのまま申請人情報が残る。 | bug報告ではフィールド名、症状、期待差分だけを記載し、実値は伏せる。必要ならダミー値に置換した抜粋を使う。 |

## データの分け方

```text
visa-eval/
  raw/
    申請書類/
    申請書類.zip
  catalog.json
  fixtures_single/
    <case_id>/
      <applicant_id>/
        scenario.json
        input/
          document_manifest.json
        expected/
          case_data.golden.json
          application_data.golden.json
          review.golden.json
        generated/
  eval/
    suites/
      single_smoke.json
```

## 役割

- `raw/`: Downloadsから移動した原資料。原本保管場所として扱い、加工しない。
- `catalog.json`: raw資料の分類結果。案件ID、文書種別、ページ数、Excelシートなどのメタデータを持つ。
- `fixtures_single/<case_id>/<applicant_id>/...`: 申請人1人=1フォームの単票ケース。まずここでPDF/Excel読取、正規case_data生成、フォーム投入JSON生成を検証する。
- `.../input/document_manifest.json`: そのケースでAIエージェントへ渡す入力資料リスト。
- `.../expected/case_data.golden.json`: 人手で完成させる正規case_dataの正解データ。
- `.../expected/application_data.golden.json`: case_dataから生成されるフォーム投入用JSONの正解データ。
- `.../expected/review.golden.json`: 不足確認・リスク判定・人レビュー要否の正解データ。現状はExcel起点のscaffoldを含むため、人手確認でgolden化する。
- `.../generated/`: AIエージェントやスクリプトが出力した結果。expectedと比較する。

## 現在のケース

- `gijinkoku_a_company_round1`: A社 1回目申請。技人国COE想定。複数申請人、雇用条件通知書、会社書類、申請人資料束、参考履歴書を含む。
- `gijinkoku_a_company_round2_family_japan`: A社 2回目申請 家族在住パターン。技人国COE想定。申請書類束、会社書類、ヒアリングシート、添付外資料、メール文脈を含む。

現在は `fixtures/` を置かず、`fixtures_single/` の単票ケースに絞る。オンライン申請フォームが1申請人=1フォームなので、まず1人分の抽出と投入JSON生成が安定するかを検証する。

## 再分類

raw配下を更新したら、以下を実行して `catalog.json` を再生成する。単票fixtureの追加・更新は、既存の `fixtures_single/` 構成を参考に個別に作る。

```bash
python3 rasens-autofill/scripts/classify_test_documents.py
```

## 評価の考え方

### Golden作成モード

1. `document_manifest.json` をCodex/AIエージェントへ渡す。
2. AIが `generated/case_data.json` と `generated/review.json` を作る。
3. `generated/case_data.json` を deterministic な変換処理に渡して `generated/application_data.json` を作る。
4. 人が `generated/*.json` を確認し、必要な補正後に `expected/*.golden.json` として確定する。

### 評価モード

1. `document_manifest.json` をAIエージェントへ渡す。
2. AIが `generated/case_data.json` と `generated/review.json` を作る。
3. `generated/case_data.json` を deterministic な変換処理に渡して `generated/application_data.json` を作る。
4. `expected/*.golden.json` と比較する。
5. 比較は、自然文全文一致ではなく、安定キー、文書種別、必須項目、レビューコードを中心に行う。

## Suite解決ルール

当面の評価スイートは `eval/suites/single_smoke.json` のみを使う。参照先は `fixtures_single/<base_case_id>/<applicant_id>/` で、1申請人=1フォームの入力生成を評価する。

## 注意

- 実在個人情報を含むため、raw資料とgenerated出力の共有範囲に注意する。
- 実案件データをChrome拡張の同梱 `application_data.json` に入れない。
- DevTools Consoleには値をマスクして出す。必要があっても実値ログを外部共有しない。
- `case_data.golden.json` は人手レビュー済みの正解データとして扱う。
- `application_data.golden.json` は派生物。案件正本ではない。
- `unused_resume` と分類された履歴書は、申請には添付しないが、記載情報（職歴・学歴等）はAI抽出の対象とする。
- `not_attached_reference` は添付外資料。差分確認・参考用として扱う。

## `fixtures_single/` について

`fixtures_single/` は、申請人1人分の評価用fixtureを置く場所です。まずここで、Codexが実PDF・Excelを読んで `case_data`、`review`、`application_data` を作れるか確認する。
