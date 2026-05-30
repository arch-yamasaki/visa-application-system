# 11 Golden data 確認ワークフロー

## 目的

`case_data.golden.json` が本当に正しいかを、人間が無理なく確認する。

eval script は「golden と generated の差分」を出せるが、golden 自体が間違っている場合は検出できない。Phase 4 の3件確認後に、goldenの正しさを別作業として確認する。

## 基本方針

最初から全項目を厳密採点しない。MVPでは、RASENS入力に直結する主要項目を優先して確認する。

```text
優先して見る:
  applicant
  entry_plan
  employer
  employment
  applicant.education
  applicant.family
  applicant.immigration_history

後回し:
  review
  bbox
  field_metadataの定量採点
```

## 確認対象

```text
visa-eval/test_cases_from_raw/<case>/<applicant>/
├─ input/document_manifest.json
├─ expected/case_data.golden.json
└─ generated/comparison_report.md
```

raw資料は `input/document_manifest.json` の `path` を見て確認する。実PIIを含むため、スクリーンショットや抜粋は `qa/` 配下に置き、gitには入れない。

## シンプルな確認手順

1. `expected/case_data.golden.json` を開く。
2. `input/document_manifest.json` で、goldenの根拠になる資料を確認する。
3. RASENSに入る主要項目だけを先に見る。
4. 明らかに資料から分からない値は、goldenから外すか空欄にする。
5. 申請書PDFだけから分かる値は、Gemini入力に渡していないなら抽出goldenに入れない。
6. 修正後に `compare_with_golden.py --targets case_data,application_data` を再実行する。

## チェックリスト

| 観点 | 確認内容 |
|---|---|
| 申請人 | 氏名、国籍、生年月日、性別、出生地、旅券番号、有効期限 |
| 入国計画 | 入国目的、上陸予定港、滞在予定期間、査証申請予定地 |
| 所属機関 | 会社名、所在地、法人番号、業種、売上、従業員数 |
| 雇用・活動 | 契約形態、就労開始日、期間、給与、職務、活動内容詳細 |
| 学歴 | 最終学歴、学校名、卒業年月、専攻 |
| 家族 | 同伴者、在日親族・同居者の有無と最大3件の明細 |
| 入管履歴 | 過去入国、COE申請歴、犯罪歴、退去強制・出国命令 |
| 固定値 | 代理人、取次者、受領方法が抽出値と混ざっていないか |

## 判断ルール

| 状況 | 対応 |
|---|---|
| 資料に明記されている | goldenに入れる |
| 複数資料で値が違う | 備考を残し、人間が採用値を決める |
| 推測で補完する値 | MVPでは入れてよいが、推測ルールをdocsへ残す |
| Gemini入力に渡していない資料だけにある | 抽出goldenからは外す |
| RASENS固定値 | `case_data.golden.json` には必要な固定値だけ残す。抽出精度評価とは分ける |

## 3ケース確認の進め方

```text
1. amit_tamang
   基本ケースとして、主要項目の正しさを見る

2. kushang_subba_limbu
   同じ会社資料で、申請人の取り違えがないか見る

3. sanjay_gautam
   家族・在日親族・同居者の項目が空欄/有無含めて妥当か見る
```

## QAコマンド

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/scripts/compare_with_golden.py \
  --generated <fixture_dir>/expected \
  --expected <fixture_dir>/expected \
  --targets case_data,application_data
```

実Gemini出力を確認する場合は、`generated/<run_id>` を指定する。

```bash
visa-app/backend/.venv/bin/python \
  visa-eval/scripts/compare_with_golden.py \
  --generated <fixture_dir>/generated/<run_id> \
  --expected <fixture_dir>/expected \
  --targets case_data,application_data
```

## リスク

- goldenが間違っていると、AI出力が正しくても不一致になる。
- 申請書PDFだけにある値をgoldenに残すと、Gemini入力条件の問題が抽出漏れに見える。
- 固定値や手入力値を抽出goldenに混ぜると、AI精度と業務設定の問題が混ざる。
- `application_data` は派生物なので、generator変更時に差分が出る。まず `case_data` の正しさを確認してから読む。
