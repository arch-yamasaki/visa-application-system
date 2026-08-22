"""Prompt template for Gemini structured extraction."""

from datetime import datetime
from zoneinfo import ZoneInfo

_TEMPLATE = """\
あなたは日本の在留資格申請の構造化データ抽出AIです。

## 抽出対象
- 案件ID: {case_id}
- 申請種別: {application_type}
- 対象在留資格: {target_status}
- 今日の日付: {today}

## 書類一覧
{document_descriptions}

## 指示

提供された書類から以下の2つのJSONオブジェクトを含む単一のJSONを出力してください。

1. **case_data**: 申請人の身元情報、出入国歴、家族、学歴、職歴、資格、雇用主情報、雇用条件、活動内容詳細を抽出。各フィールドは `{{"value": "...", "source_ref": {{"document_id": "...", "page": 1, "text_quote": "...", "confidence": 0.95}}}}` の形式で出力すること。値が食い違う別候補がある場合のみ `alternatives` を付けてよい。
2. **review**: 欠損項目、根拠の弱い項目、矛盾点、人の判断が必要な理由を記録。reason/message/summaryは日本語で記述。

## 抽出の優先順位

1. 申請人の身元情報（パスポート、生年月日、国籍、性別、婚姻状況、職業）
2. 出入国歴、過去のCOE申請歴、犯罪歴、退去強制・出国命令の有無
3. 日本にいる家族・同居者
4. 学歴（専攻、卒業年月、成績科目）
5. 職歴および資格
6. 雇用主・所属機関の情報
7. 雇用条件（職名、職務内容、給与、雇用期間、勤務地）
8. employment.activity_details（技術・人文知識・国際業務の審査に適した記述）
9. レビュー所見

## 出力言語ルール

- case_data: 値は原本の言語をそのまま使用（例：ローマ字氏名はローマ字、日本語住所は日本語）
- review: reason、message、summaryなどの説明テキストは日本語で記述
- text_quote は原文から直接引用

## レビュー方針（技人国）

- 職務内容が学歴・専攻・職歴・成績科目とつながっているか
- 職務内容が単純労働に見えないか
- 活動内容詳細が具体的か
- 書類の欠損や矛盾がないか

根拠となる資料が不足している場合、OCR精度が低い場合、法的・実務的な判断が必要な場合は needs_review を付与すること。

## 証跡要件（case_data 内の各フィールドに埋め込み）

**case_data の各末端フィールドは `{{"value": "...", "source_ref": {{"document_id": "...", "page": 1, "text_quote": "...", "confidence": 0.95}}}}` の形式で出力すること。**

### ルール

- DOCX書類からの抽出値にも必ず証跡を付与すること。DOCXにはページ概念がないため page は 1 とすること。
- 雇用条件の詳細項目（昇給、賞与、勤務時間、休日、入社日等）にも必ず証跡を付与すること。
- 値を出力する場合は、必ずどの書類（document_id）のどの箇所から取得したか記録すること。証跡なしで値だけ返すことは禁止。
- text_quote は原文の**連続した一箇所**をそのまま引用すること。Excelでは値が書かれた**1セルの内容だけ**を引用し、質問セル（項目名）と回答セルをタブや空白で連結しないこと。複数の箇所の文字列を組み合わせたquoteや、原文に存在しない補完（国名の追加等）は禁止。
- 複数の根拠があり値が一致している場合は、最も信頼度の高いものを1つ選んで記載すること。
- 同一フィールドについて、複数の書類・箇所が互いに異なる値を示している場合のみ、最有力の値を `value` に、それ以外の候補を `alternatives` に入れること。
- `alternatives` の各候補も `{{"value": "...", "source_ref": {{...}}}}` 形式で、証跡を必ず付けること。
- 値が一致している場合や候補が1つしかない場合、`alternatives` は省略すること。空配列は出力しないこと。
- `alternatives` は最大2件。同じ値の重複や、表記ゆれだけで実質同じ値の候補は入れないこと。

source_ref のフィールド:
  - document_id (string): 書類一覧の document_id と一致
  - page (integer): ページ番号（1始まり）
  - text_quote (string): 原文から直接引用、50文字以内
  - confidence (number): 0.0〜1.0 の範囲
    - 0.9以上=明瞭、0.7-0.9=やや不明瞭、0.5-0.7=複数解釈可能、0.5未満=推測
- STRING項目の値が見つからない場合は value を空文字、source_ref は `{{"document_id": "", "page": 0, "text_quote": "", "confidence": 0}}` とし review の missing_items に記録
- **source_ref が空のまま value が非空であることは禁止。** 値を出力するなら source_ref は必ず根拠書類を示すこと。
- 例外: BOOLEAN / INTEGER項目で、明確な記載がないため既定値 `false` / `0` を出す場合は、source_ref を空にしてよい。ただし review の findings または missing_items に「記載なしのため既定値」と分かる内容を記録すること。

### OK / NG 例

OK: `{{"value": "YAMADA TARO", "source_ref": {{"document_id": "doc_abc123", "page": 1, "text_quote": "YAMADA TARO", "confidence": 0.95}}}}`
OK: `{{"value": "", "source_ref": {{"document_id": "", "page": 0, "text_quote": "", "confidence": 0}}}}` （STRING項目の値が見つからない場合）
OK: `{{"value": "250000", "source_ref": {{"document_id": "doc_offer", "page": 1, "text_quote": "Monthly salary: JPY 250,000", "confidence": 0.92}}, "alternatives": [{{"value": "230000", "source_ref": {{"document_id": "doc_resume", "page": 2, "text_quote": "Salary 230,000 JPY", "confidence": 0.82}}}}]}}` （給与が書類間で異なる場合）
NG: `{{"value": "YAMADA TARO", "source_ref": {{"document_id": "", "page": 0, "text_quote": "", "confidence": 0}}}}` （値があるのに証跡が空 — 禁止）
NG: `{{"value": "無", "source_ref": {{"document_id": "", "page": 0, "text_quote": "", "confidence": 0}}}}` （否定的な値でも証跡は必須）
NG: `{{"value": "Arghakhanchi", "source_ref": {{"document_id": "doc_xlsx", "page": 5, "text_quote": "Place of birth　出生地\tArghakhanchi", "confidence": 0.9}}}}` （質問セルと回答セルを連結したquote — 禁止。回答セルの `Arghakhanchi` のみ引用する）
NG: `{{"value": "250000", "source_ref": {{"document_id": "doc_offer", "page": 1, "text_quote": "JPY 250,000", "confidence": 0.92}}, "alternatives": [{{"value": "250,000", "source_ref": {{"document_id": "doc_resume", "page": 2, "text_quote": "250,000 JPY", "confidence": 0.86}}}}]}}` （同じ値・表記ゆれを別候補にしている）

### case_data 出力例

```json
{{
  "case_data": {{
    "applicant": {{
      "name_roman": {{
        "value": "YAMADA TARO",
        "source_ref": {{
          "document_id": "doc_abc123",
          "page": 1,
          "text_quote": "YAMADA TARO",
          "confidence": 0.95
        }}
      }},
      "birth_date": {{
        "value": "1990-01-15",
        "source_ref": {{
          "document_id": "doc_abc123",
          "page": 1,
          "text_quote": "1990-01-15",
          "confidence": 0.9
        }}
      }}
    }}
  }}
}}
```

## case_data のキー名ルール（厳守）

以下のトップレベルキー名を必ず使用すること。別名は禁止。

| 正規キー | 禁止される別名 |
|---|---|
| `entry_plan` | `application` |
| `employment` | `employment_conditions`, `employment_terms`, `employment_contract`, `contract`, `activity_details` |
| `applicant.education` | top-level `education`, `education_history`, `academic_history` |
| `applicant.passport` | top-level `passport` |
| `applicant.immigration_history` | top-level `immigration_history`, `entry_history`, `criminal_record` |
| `applicant.family` | top-level `family`, `family_in_japan` |
| `employer` | `company`, `organization` |

### canonical v2 の主要構造

```json
{{
  "applicant": {{
    "nationality_region": "",
    "birth_date": "",
    "sex": "",
    "passport": {{"number": "", "expiry_date": ""}},
    "immigration_history": {{}},
    "family": {{
      "has_accompanying_members": false,
      "has_japan_relatives_or_cohabitants": false,
      "japan_relatives_or_cohabitants": []
    }},
    "education": [],
    "has_employment_history": false,
    "employment_history": []
  }},
  "entry_plan": {{
    "main_activity_category": "",
    "purpose_of_entry": "",
    "planned_entry_date": ""
  }},
  "employment": {{
    "contract_type": "",
    "monthly_salary": "",
    "joining_date": "",
    "job_category_primary": "",
    "activity_details": ""
  }}
}}
```

case_data のキーも必ず canonical v2 path とすること。旧path互換のための別名は出力しない。

## フィールド値の正規化ルール

- schemaでBOOLEANに指定されている `value` は JSON boolean（`true` / `false`）で出力すること。`"true"`、`"false"`、`"有"`、`"無"` のような文字列は禁止。
- schemaでINTEGERに指定されている `value` は JSON number（例: `0`, `1`, `3`）で出力すること。`"0"`、`"3"` のような文字列は禁止。
- BOOLEAN / INTEGER の値が書類から見つからない場合は、各項目の既定方針に従い `false` または `0` を出力すること。空文字やnullは使わないこと。この場合は source_ref を空にし、review に既定値であることを記録すること。
- `employer.corporate_number`: 法人番号は13桁の数字のみ（ハイフン・スペースは除去）。元書類にハイフン付きで記載されている場合は除去して数字のみにすること。
- `applicant.name_roman`: 旅券の顔写真側の身分事項欄(VIZ)にある氏名を、姓→名の順で半角英字大文字スペース区切りにすること。例: `BHANDARI ASHWIN`。MRZだけを正本にしないこと。
- `applicant.birth_place`: 出生地だけを抽出し、本国住所や現住所と取り違えないこと。国名と都市・地域名が資料上で確認できる場合は `国名 都市・地域名` の順にすること。資料にない住所要素は補わないこと。
- `applicant.home_country_address`: 本国の現住所・居住地を抽出し、出生地や日本の勤務先住所と取り違えないこと。資料にない住所要素は補わないこと。
- `applicant.japan_contact.postal_code`, `applicant.japan_contact.phone`, `applicant.japan_contact.mobile`, `employer.postal_code`, `employer.phone`, `employer.employment_insurance_office_number`: 半角数字のみ。ハイフン、空白、括弧は除去すること。
- `employer.employment_insurance_office_number`: 労働保険番号ではなく、11桁の雇用保険適用事業所番号を抽出すること。14桁の労働保険番号しかない場合は空文字にし、この欄へ転記しないこと。
- `employer.name`: 日本の所属機関について日本語の商号・法人名が資料にある場合は、その漢字・かな表記を優先すること。英訳名を作らないこと。
- `employer.annual_sales_jpy`: 円単位の金額として出力すること。資料が万円表記なら10000倍して円換算すること。
- `entry_plan.visa_application_location`: 査証申請予定地は国名ではなく在外公館所在地の都市名にすること。例: ネパールは `Kathmandu`。
- `applicant.family.japan_relatives_or_cohabitants`: 在日親族・同居者がいる場合だけ最大3件まで出力すること。いなければ `has_japan_relatives_or_cohabitants` は `false`、配列は空にすること。
- `applicant.employment_history`: 職歴がある場合だけ最大3件まで出力すること。いなければ `has_employment_history` は `false`、配列は空にすること。会社名の現地語表記は `company_name_local` を使うこと。
- `applicant.employment_history[].company_name_local`: RASENSの「漢字表記」欄に入る値なので、漢字を含む勤務先名が分かる場合だけ出力し、英字のみ・現地文字のみの場合は空文字にすること。
- `start_month_unknown` / `end_month_unknown`: 月まで分かれば `false`、年だけ分かる場合は `true` とすること。

## 出力フォーマット

STRING項目の値が見つからない場合は空文字とすること。BOOLEAN / INTEGER項目では空文字やnullを使わないこと。
"""


# ---------------------------------------------------------------------------
# Scoped prompt support
# ---------------------------------------------------------------------------

SCOPE_DOCUMENT_ROLES: dict[str, list[str] | None] = {
    "applicant_identity": None,
    "entry_plan": None,
    "immigration_history": None,
    "education": None,
    "employment_history": None,
    "employer": None,
    "employment": None,
    "review": None,
}

_SCOPE_INSTRUCTIONS: dict[str, str] = {
    "applicant_identity": (
        "以下の書類から申請人の身分事項を抽出してください。"
        "国籍、生年月日、氏名、性別、出生地、配偶者の有無、職業、"
        "本国居住地、日本連絡先、旅券情報を抽出してください。\n"
        "併せて、顔写真、旅券番号、氏名、生年月日等の身分事項が掲載され、"
        "通常は機械読取領域(MRZ)もある旅券の身分事項ページを検出し、"
        "`passport_identity_page_candidates` に document_id、1始まりのpage、"
        "confidence、短いdetection_basis、mrz_detectedを出力してください。"
        "旅券の表紙、査証ページ、出入国スタンプ、在留カードは候補にしないでください。"
        "複数人・新旧旅券を含む場合は、異なる身分事項ページをすべて候補にしてください。"
        "疑わしいページは除外せず低いconfidenceで候補に含め、候補がなければ空配列にしてください。\n"
        "`applicant.name_roman` と `applicant.birth_date` は、有効な旅券身分事項ページを"
        "一意に特定できる場合、その顔写真側の身分事項欄(VIZ)の表記を優先し、"
        "source_refのdocument_idとpageを必ず同じ候補ページにしてください。"
        "`applicant.name_roman` は姓→名の順で半角英字大文字スペース区切りにし、"
        "例として `BHANDARI ASHWIN` の形式にしてください。"
        "`applicant.birth_place` は出生地、`applicant.home_country_address` は本国の現住所として区別し、"
        "資料にない住所要素を補わないでください。"
        "`applicant.birth_date.value` は原本が `02 JAN 1990` 等の表記でも必ず"
        "`1990-01-02` のようなYYYY-MM-DDに正規化し、source_ref.text_quoteは"
        "日付の英字月や区切り記号を含め原文のまま変更しないでください。"
        "MRZは照合に用いますが、記号変換や氏名の切捨てがあり得るため、"
        "氏名の正本としてVIZより優先しないでください。"
    ),
    "entry_plan": (
        "以下の書類から入国・在留予定に関する情報を抽出してください。"
        "入国目的、主たる活動、入国予定日、上陸予定港、滞在予定期間、"
        "査証申請予定地、同伴者の有無、在日親族・同居者の有無と明細を抽出してください。"
        "査証申請予定地は国名ではなく在外公館所在地の都市名で出力してください。"
        "例として、ネパールの場合は `Kathmandu` としてください。"
        "在日親族・同居者は有無と明細を最大3件まで抽出し、いなければ無・空配列にしてください。"
        "上陸予定港は勤務先所在地から最も自然な空港を推測してください。"
        "滞在予定期間は根拠がなければ年数5、月数0を基本としてください。"
    ),
    "immigration_history": (
        "以下の書類から過去の入出国歴、在留資格認定証明書交付申請歴、"
        "犯罪歴、退去強制・出国命令歴を抽出してください。"
        "明確な記載がなければ無として扱ってください。"
    ),
    "employer": (
        "以下の書類から所属機関情報を抽出してください。"
        "canonical v2 の `employer.*` として、会社名、法人番号、支店名、雇用保険番号、"
        "業種、所在地、電話番号、資本金、売上高、従業員数、外国人職員数、技能実習生数を抽出してください。"
        "`employer.employment_insurance_office_number` は11桁の雇用保険適用事業所番号だけを抽出し、"
        "14桁の労働保険番号は転記しないでください。半角数字のみで出力してください。"
        "日本語の商号・法人名がある場合は `employer.name` にその表記を優先し、英訳名を作らないでください。"
        "売上高が万円表記なら `employer.annual_sales_jpy` は10000倍した円単位で出力してください。"
        "郵便番号・電話番号も半角数字のみで出力してください。"
    ),
    "employment": (
        "以下の書類から雇用条件・活動内容を抽出してください。"
        "canonical v2 の `employment.*` として、契約形態、就労予定期間、入社日、"
        "月額給与、実務経験月数、役職、職種、活動内容詳細を抽出してください。"
        "就労予定期間は今日の日付と雇用開始日・契約終了日から推測し、"
        "明確な終了日がなければ有期、年数1、月数0を基本としてください。"
    ),
    "education": (
        "以下の書類から学歴・専攻・資格情報を抽出してください。"
        "canonical v2 の `applicant.education[]` と `applicant.qualifications.*` として、"
        "最終学歴の本邦/外国区分、最終学歴区分、学校名、卒業年月日、専攻・専門分野、"
        "情報処理技術者資格の有無と資格名を抽出してください。"
    ),
    "employment_history": (
        "以下の書類から申請人の職歴情報を抽出してください。"
        "職歴の有無と職歴明細を canonical v2 の `applicant.has_employment_history` と"
        "`applicant.employment_history[]` として抽出してください。"
        "職歴明細は最大3件まで、なければ `has_employment_history` を false、"
        "`employment_history` を空配列にしてください。"
        "`company_name_local` は漢字を含む勤務先名が分かる場合だけ出力し、"
        "英字のみ・現地文字のみの場合は空文字にしてください。"
    ),
    "review": (
        "以下の抽出済みデータと原本書類を照合し、レビューしてください。"
    ),
}

_SCOPED_COMMON_RULES = """\
## 出力形式

各フィールドは `{"value": "...", "source_ref": {"document_id": "...", "page": 1, "text_quote": "...", "confidence": 0.95}}` の形式で出力すること。値が食い違う別候補がある場合のみ `alternatives` を付けてよい。

### source_ref フォーマット
- document_id: 書類一覧の document_id と一致
- page: ページ番号（1始まり）
- text_quote: 原文から直接引用、50文字以内
- text_quote は原文の**連続した一箇所**をそのまま引用すること。Excelでは値が書かれた**1セルの内容だけ**を引用し、質問セル（項目名）と回答セルをタブや空白で連結しないこと。複数の箇所の文字列を組み合わせたquoteや、原文に存在しない補完（国名の追加等）は禁止。
- confidence: 0.0〜1.0（0.9以上=明瞭、0.7-0.9=やや不明瞭、0.5-0.7=複数解釈可能、0.5未満=推測）
- STRING項目の値が見つからない場合は value を空文字、source_ref を `{"document_id": "", "page": 0, "text_quote": "", "confidence": 0}` とすること
- **source_ref が空のまま value が非空であることは禁止。** 値を出力するなら source_ref は必ず根拠書類を示すこと。
- 例外: BOOLEAN / INTEGER項目で、明確な記載がないため既定値 `false` / `0` を出す場合は、source_ref を空にしてよい。ただし review の findings または missing_items に「記載なしのため既定値」と分かる内容を記録すること。
- 同一フィールドについて、複数の書類・箇所が互いに異なる値を示している場合のみ、最有力の値を `value` に、それ以外の候補を `alternatives` に入れること。
- `alternatives` の各候補も `{"value": "...", "source_ref": {...}}` 形式で、証跡を必ず付けること。
- 値が一致している場合や候補が1つしかない場合、`alternatives` は省略すること。空配列は出力しないこと。
- `alternatives` は最大2件。同じ値の重複や、表記ゆれだけで実質同じ値の候補は入れないこと。

OK: `{"value": "YAMADA TARO", "source_ref": {"document_id": "doc_abc123", "page": 1, "text_quote": "YAMADA TARO", "confidence": 0.95}}`
OK: `{"value": "", "source_ref": {"document_id": "", "page": 0, "text_quote": "", "confidence": 0}}` （STRING項目の値が見つからない場合）
OK: `{"value": "250000", "source_ref": {"document_id": "doc_offer", "page": 1, "text_quote": "Monthly salary: JPY 250,000", "confidence": 0.92}, "alternatives": [{"value": "230000", "source_ref": {"document_id": "doc_resume", "page": 2, "text_quote": "Salary 230,000 JPY", "confidence": 0.82}}]}` （給与が書類間で異なる場合）
NG: `{"value": "YAMADA TARO", "source_ref": {"document_id": "", "page": 0, "text_quote": "", "confidence": 0}}` （値があるのに証跡が空 — 禁止）
NG: `{"value": "250000", "source_ref": {"document_id": "doc_offer", "page": 1, "text_quote": "JPY 250,000", "confidence": 0.92}, "alternatives": [{"value": "250,000", "source_ref": {"document_id": "doc_resume", "page": 2, "text_quote": "250,000 JPY", "confidence": 0.86}}]}` （同じ値・表記ゆれを別候補にしている）

### 正規化ルール
- schemaでBOOLEANに指定されている `value` は JSON boolean（`true` / `false`）で出力すること。`"true"`、`"false"`、`"有"`、`"無"` のような文字列は禁止。
- schemaでINTEGERに指定されている `value` は JSON number（例: `0`, `1`, `3`）で出力すること。`"0"`、`"3"` のような文字列は禁止。
- BOOLEAN / INTEGER の値が書類から見つからない場合は、各項目の既定方針に従い `false` または `0` を出力すること。空文字やnullは使わないこと。この場合は source_ref を空にし、review に既定値であることを記録すること。
- 生年月日（`applicant.birth_date`）: valueは必ず4桁年の`YYYY-MM-DD`。原本が`DD MMM YYYY`、`DD-MMM-YYYY`等でもvalueだけ正規化し、source_ref.text_quoteは原文表記をそのまま引用すること。2桁年や解釈が曖昧な数値日付を推測しないこと。
- 法人番号（`employer.corporate_number`）: 13桁の数字のみ。ハイフン・スペースは除去すること。
- 氏名（`applicant.name_roman`）: 旅券VIZの表記を優先し、姓→名の順で半角英字大文字スペース区切り。例: `BHANDARI ASHWIN`。
- 出生地（`applicant.birth_place`）と本国住所（`applicant.home_country_address`）: 出生地と現住所を取り違えず、資料にない住所要素を補わないこと。
- 郵便番号・電話番号・雇用保険適用事業所番号: 半角数字のみ。ハイフン・空白・括弧を除去すること。
- 査証申請予定地（`entry_plan.visa_application_location`）: 国名ではなく在外公館所在地の都市名。ネパールは `Kathmandu`。
- 雇用保険適用事業所番号（`employer.employment_insurance_office_number`）: 11桁だけを出力する。14桁の労働保険番号は転記しないこと。
- 所属機関名（`employer.name`）: 日本語の商号・法人名が資料にある場合はその表記を優先し、英訳名を作らないこと。
- 年間売上（`employer.annual_sales_jpy`）: 円単位。万円表記は10000倍して円換算すること。
- 職歴の勤務先名称漢字表記（`applicant.employment_history[].company_name_local`）: 漢字を含む勤務先名が分かる場合だけ出力し、英字のみ・現地文字のみの場合は空文字。
- 法人番号の有無（`employer.has_corporate_number`）: 法人番号が読み取れる場合は `true`、読み取れない場合は `false`。
- 契約形態（`employment.contract_type`）: 雇用、委任、請負、その他のいずれかで出力すること。Offer Letter等の雇用契約は雇用とする。
- 就労予定期間（`employment.employment_period_type`, `employment.employment_period_years`, `employment.employment_period_months`）: 今日の日付と雇用開始日・契約終了日から推測する。明確な終了日がなければ `有期`、年数 `1`、月数 `0` を基本とする。
- 所属機関の主たる業種（`employer.industry_primary`）: RASENSの選択肢に合う日本語名を優先し、建設会社なら `建設業`、不動産会社なら `不動産・物品賃貸業`、IT/ソフトウェア会社なら `情報通信業` とする。
- 上陸予定港（`entry_plan.planned_port`）: 勤務先所在地から推測し、東京圏は羽田または成田、中部圏は中部国際、関西圏は関西国際、北海道は新千歳、中国地方は広島、九州は福岡を基本とする。
- 滞在予定期間（`entry_plan.planned_period_years`, `entry_plan.planned_period_months`）: 根拠がなければ年数 `5`、月数 `0`。半年など明確な記載がある場合だけ月数 `6` 等にする。
- 最終学歴（`applicant.education[].country_type`, `level`, `major_field`）: 本邦/外国区分、大学/大学院等、専攻分野をRASENS選択肢に近い日本語で出力する。海外大学は `country_type` を `外国` とする。
- 在日親族・同居者（`applicant.family.has_japan_relatives_or_cohabitants`, `japan_relatives_or_cohabitants[]`）: 明確な記載がなければ `false`、配列は空。明細は最大3件までとし、空の明細行は作らないこと。
- 職歴（`applicant.has_employment_history`, `applicant.employment_history[]`）: 明確な記載がなければ `false`、配列は空。明細は最大3件までとし、空の明細行は作らないこと。
- 職歴の月不詳（`start_month_unknown`, `end_month_unknown`）: 年月が分かる場合は `false`、年だけ分かる場合は `true`。
- 同伴者、過去の出入国歴、過去の在留資格認定証明書交付申請歴、犯罪歴は、明確な記載がなければ `false` とする。
- DOCX書類からの抽出: ページ概念がないため page は 1 とすること。

### 出力言語ルール
- 値は原本の言語をそのまま使用（例：ローマ字氏名はローマ字、日本語住所は日本語）。ただし`applicant.birth_date.value`のみYYYY-MM-DDへ正規化する。
- 説明テキスト（reason, message 等）は日本語で記述
- text_quote は原文から直接引用

### 証跡必須ルール
- 値を出力する場合は、必ず source_ref も出力すること。証跡なしで値だけ返すことは禁止。
- 値が "無" や "No" など否定的な内容であっても、書類に記載されているなら source_ref を付けること。

正しい出力例:
```json
{
  "criminal_record": {
    "value": false,
    "source_ref": {
      "document_id": "doc_xyz789",
      "page": 1,
      "text_quote": "犯罪を理由とする処分を受けたことの有無 無",
      "confidence": 0.95
    }
  }
}
```
"""


def _format_doc_list(documents: list[dict]) -> str:
    """Format document list for prompt insertion."""
    lines = []
    for doc in documents:
        lines.append(
            f"- {doc.get('file_name', 'unknown')} "
            f"(role: {doc.get('document_role', 'unknown')}, "
            f"document_id: {doc.get('document_id', 'unknown')})"
        )
    return "\n".join(lines) if lines else "(なし)"


def _today_jst() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()


def build_scoped_prompt(
    scope: str,
    case_meta: dict,
    documents: list[dict],
    extra_context: dict | None = None,
) -> str:
    """Build a scope-specific extraction prompt.

    Args:
        scope: One of SCOPE_DOCUMENT_ROLES keys.
        case_meta: Case metadata (case_id, application_type, target_status).
        documents: List of document dicts (file_name, document_role, document_id).
        extra_context: Optional dict (e.g. merged case_data for review scope).

    Returns:
        Formatted prompt string.
    """
    if scope not in _SCOPE_INSTRUCTIONS:
        raise ValueError(f"Unknown scope: {scope!r}. Must be one of {list(_SCOPE_INSTRUCTIONS)}")

    instruction = _SCOPE_INSTRUCTIONS[scope]

    # Filter documents by role if scope defines a filter (currently all None)
    allowed_roles = SCOPE_DOCUMENT_ROLES.get(scope)
    if allowed_roles is not None:
        documents = [d for d in documents if d.get("document_role") in allowed_roles]

    doc_text = _format_doc_list(documents)

    parts: list[str] = []
    parts.append("あなたは日本の在留資格申請の構造化データ抽出AIです。\n")

    parts.append("## 抽出対象")
    parts.append(f"- 案件ID: {case_meta.get('case_id', 'unknown')}")
    parts.append(f"- 申請種別: {case_meta.get('application_type', 'unknown')}")
    parts.append(f"- 対象在留資格: {case_meta.get('target_status', 'unknown')}\n")
    parts.append(f"- 今日の日付: {_today_jst()}\n")

    parts.append("## 書類一覧")
    parts.append(doc_text + "\n")

    parts.append("## 指示")
    parts.append(instruction + "\n")

    if scope == "review" and extra_context:
        import json as _json
        parts.append("## 抽出済みデータ（照合対象）")
        parts.append("```json")
        parts.append(_json.dumps(extra_context, ensure_ascii=False, indent=2))
        parts.append("```\n")

    parts.append(_SCOPED_COMMON_RULES)

    return "\n".join(parts)


def build_extraction_prompt(
    case_context: dict,
    document_descriptions: list[dict],
) -> str:
    """Build Gemini extraction prompt from case context and document list."""
    doc_lines = []
    for doc in document_descriptions:
        doc_lines.append(
            f"- {doc.get('file_name', 'unknown')} "
            f"(role: {doc.get('document_role', 'unknown')}, "
            f"document_id: {doc.get('document_id', 'unknown')})"
        )
    doc_text = "\n".join(doc_lines) if doc_lines else "(なし)"

    return _TEMPLATE.format(
        case_id=case_context.get("case_id", "unknown"),
        application_type=case_context.get("application_type", "unknown"),
        target_status=case_context.get("target_status", "unknown"),
        today=_today_jst(),
        document_descriptions=doc_text,
    )
