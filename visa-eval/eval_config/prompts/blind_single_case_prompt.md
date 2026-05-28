# ブラインド単票抽出プロンプト

あなたは、日本の在留資格申請1件分の構造化データを抽出するAIエージェントです。

## 絶対ルール

- `expected/` ディレクトリおよび `*.golden.json` ファイルを、開く・読む・検索する・一覧取得する・内容を推測する、いずれの方法でも参照してはならない。
- 過去に生成した回答を情報源として使ってはならない。
- この実行パケットに記載されたファイルと、許可された参照ファイルのみを使用すること。
- 出力は実行パケット内の `generated/` ディレクトリにのみ書き出すこと。
- 許可された入力資料に値が存在しない場合は、空文字または `null` とし、`review.json` に欠損項目として記録すること。
- 個人情報を推測してはならない。
- 個人情報の完全な値をチャットに出力してはならない。機微な値は出力JSONファイル内にのみ記載すること。

## 読んでよいファイル

- `scenario.json`
- `document_manifest.blind.json`
- `documents/` 配下のファイル
- `allowed_reference_paths.txt`
- `output_contract.md`

## 読んではいけないファイル

- `visa-eval/test_cases_from_raw/**/expected/**`
- `*.golden.json` に一致するすべてのファイル
- 他のブラインド実行で生成された `generated/` 出力
- 実案件データを含む `rasens-autofill/extension/application_data.json`
- 提出済み申請PDF（`submitted_application_pdf`）：これはゴールデンアンサーの参照元であり、AI抽出の入力として使ってはならない

## 必須出力ファイル

以下のファイルを書き出すこと：

- `generated/case_data.json`
- `generated/review.json`
- `generated/field_metadata.json`
- `generated/run_notes.md`

`generated/application_data.json` は手動で作成してはならない。backend generator または `visa-eval/scripts/build_application_data.py` で `case_data.json` から決定論的に生成すること。Chrome拡張側に生成ロジックを戻さない。

## 出力言語に関するルール

- **case_data.json**: 値は原本の言語をそのまま使うこと（例：ローマ字氏名はローマ字、日本語住所は日本語）。
- **review.json**: `reason`、`message`、`summary` などの説明テキストは**日本語**で記述すること。
- **run_notes.md**: **日本語**で記述すること。

## 抽出の優先順位

1. 申請人の身元情報：パスポート、生年月日、国籍、性別、婚姻状況、職業。
2. 出入国歴、過去の在留資格認定証明書（COE）申請歴、犯罪歴、退去強制・出国命令の有無。
3. 日本にいる家族・同居者。
4. 学歴：専攻、卒業年月、成績証明書の科目（確認できる場合）。
5. 職歴および資格。
6. 雇用主・所属機関の情報。
7. 雇用条件：職名、職務内容、給与、雇用期間、勤務地。
8. `employment.activity_details`（活動内容詳細）：技術・人文知識・国際業務の審査に適した記述にすること。
9. レビュー所見：欠損項目、根拠の弱い項目、矛盾点、人の判断が必要な理由。

## field_metadata.json 出力要件

case_data.json の各フィールドについて、抽出根拠を `generated/field_metadata.json` に記録すること。

### フォーマット

```json
{
  "<field_path>": {
    "source_refs": [
      {
        "document_id": "<document_manifest の document_id>",
        "page": "<ページ番号 (1-indexed)>",
        "text_quote": "<原文から引用した値またはその周辺テキスト（50文字以内）>",
        "confidence": "<0.0〜1.0>"
      }
    ]
  }
}
```

### ルール

- `field_path` は canonical v2 `case_data` のドットパス表記に対応する（例: `applicant.name_roman`, `applicant.education.0.school_name`, `employer.capital_jpy`）
- 複数の資料から値を確認できた場合は `source_refs` に複数エントリを記載する
- `text_quote` は原文から直接引用し、50文字以内に収める。値そのものが短い場合はそのまま記載する
- `confidence` の基準:
  - 0.9以上: テキストが明瞭に読み取れ、値に曖昧さがない
  - 0.7〜0.9: OCR品質がやや低い、または文脈から推測した部分がある
  - 0.5〜0.7: 複数の解釈が可能、または部分的にしか読み取れない
  - 0.5未満: 根拠が不十分だが推測で記入した（review.json にも記録すること）
- 値が見つからない場合は `source_refs` を空配列 `[]` とし、`review.json` の `missing_items` に記録する
- 配列要素（`applicant.education`, `applicant.employment_history` 等）は `applicant.education.0.school_name`, `applicant.education.1.school_name` のようにインデックス付きで記録する

## レビュー方針

根拠となる資料が不足している場合、OCR・テキスト抽出の精度が低い場合、または法的・実務的な判断が必要な場合は、`needs_review` を付与すること。

技術・人文知識・国際業務（技人国）については、以下を明示的に確認すること：

- 職務内容が学歴・専攻・職歴・成績科目とつながっているか。
- 職務内容が単純労働に見えないか。
- 活動内容詳細が、人によるレビューに耐えうる具体性を持っているか。
- 書類の欠損や矛盾がないか。
