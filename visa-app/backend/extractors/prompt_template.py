"""Prompt template for Gemini structured extraction."""

_TEMPLATE = """\
あなたは日本の在留資格申請の構造化データ抽出AIです。

## 抽出対象
- 案件ID: {case_id}
- 申請種別: {application_type}
- 対象在留資格: {target_status}

## 書類一覧
{document_descriptions}

## 指示

提供された書類から以下の2つのJSONオブジェクトを含む単一のJSONを出力してください。

1. **case_data**: 申請人の身元情報、出入国歴、家族、学歴、職歴、資格、雇用主情報、雇用条件、活動内容詳細を抽出。各フィールドは `{{"value": "...", "source": "document_id|page|text_quote|confidence"}}` の形式で出力すること。
2. **review**: 欠損項目、根拠の弱い項目、矛盾点、人の判断が必要な理由を記録。reason/message/summaryは日本語で記述。

## 抽出の優先順位

1. 申請人の身元情報（パスポート、生年月日、国籍、性別、婚姻状況、職業）
2. 出入国歴、過去のCOE申請歴、犯罪歴、退去強制・出国命令の有無
3. 日本にいる家族・同居者
4. 学歴（専攻、卒業年月、成績科目）
5. 職歴および資格
6. 雇用主・所属機関の情報
7. 雇用条件（職名、職務内容、給与、雇用期間、勤務地）
8. activity_details（技術・人文知識・国際業務の審査に適した記述）
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

**case_data の各末端フィールドは `{{"value": "...", "source": "document_id|page|text_quote|confidence"}}` の形式で出力すること。**

### ルール

- DOCX書類からの抽出値にも必ず証跡を付与すること。DOCXにはページ概念がないため page は 1 とすること。
- 雇用条件の詳細項目（昇給、賞与、勤務時間、休日、入社日等）にも必ず証跡を付与すること。
- 値を出力する場合は、必ずどの書類（document_id）のどの箇所から取得したか記録すること。証跡なしで値だけ返すことは禁止。
- 複数の根拠がある場合は、最も信頼度の高いものを1つ選んで記載すること。

source 文字列のフォーマット: `document_id|page|text_quote|confidence`
  - document_id (string): 書類一覧の document_id と一致
  - page (integer): ページ番号（1始まり）
  - text_quote (string): 原文から直接引用、50文字以内。パイプ文字(|)は含めない
  - confidence (number): 0.0〜1.0 の範囲
    - 0.9以上=明瞭、0.7-0.9=やや不明瞭、0.5-0.7=複数解釈可能、0.5未満=推測
- 値が見つからない場合は value を空文字、source を空文字とし review の missing_items に記録

### case_data 出力例

```json
{{
  "case_data": {{
    "applicant": {{
      "name_roman": {{
        "value": "YAMADA TARO",
        "source": "doc_abc123|1|YAMADA TARO|0.95"
      }},
      "date_of_birth": {{
        "value": "1990-01-15",
        "source": "doc_abc123|1|1990-01-15|0.9"
      }}
    }}
  }}
}}
```

## case_data のキー名ルール（厳守）

以下のトップレベルキー名を必ず使用すること。別名は禁止。

| 正規キー | 禁止される別名 |
|---|---|
| `employment_conditions` | `employment_terms`, `employment_contract` |
| `education` | `education_history`, `academic_history` |
| `employer` | `company`, `organization` |

### employment_conditions の必須サブキー

```json
{{
  "employment_conditions": {{
    "company_name": "",
    "job_title": "",
    "duties": "",
    "monthly_salary": "",
    "annual_salary": "",
    "bonus": "",
    "allowances": "",
    "contract_type": "",
    "contract_period": "",
    "contract_start_date": "",
    "contract_end_date": "",
    "working_hours": "",
    "holidays": "",
    "work_location": "",
    "joining_date": "",
    "insurance": ""
  }}
}}
```

case_data のキーも必ず `employment_conditions.xxx` とすること（`employment_terms.xxx` や `employment_contract.xxx` は禁止）。

## フィールド値の正規化ルール

- `employer.corporate_number`: 法人番号は13桁の数字のみ（ハイフン・スペースは除去）。元書類にハイフン付きで記載されている場合は除去して数字のみにすること。

## 出力フォーマット

値が見つからない場合は空文字またはnullとすること。
"""


# ---------------------------------------------------------------------------
# Scoped prompt support
# ---------------------------------------------------------------------------

SCOPE_DOCUMENT_ROLES: dict[str, list[str] | None] = {
    "identity": None,   # 全書類（パスポート情報がどこにあるかわからない）
    "employer": None,    # 全書類（会社情報が複数書類に散在）
    "education": None,   # 全書類（卒業証明書がどのファイルかわからない）
    "review": None,      # 全書類
}

_SCOPE_INSTRUCTIONS: dict[str, str] = {
    "identity": (
        "以下の書類から申請人の身分事項を抽出してください。"
        "国籍、生年月日、氏名、性別、出生地、配偶者の有無、職業、"
        "本国居住地、日本連絡先、旅券情報、入国目的、入国予定日、"
        "上陸予定港、滞在予定期間、同伴者の有無、査証申請予定地、"
        "出入国歴、在留資格認定証明書交付申請歴、犯罪歴、退去強制歴を抽出してください。"
    ),
    "employer": (
        "以下の書類から所属機関・雇用条件・活動内容を抽出してください。"
        "契約形態、会社名、法人番号、支店名、雇用保険番号、業種、所在地、"
        "電話番号、資本金、売上高、従業員数、外国人職員数、技能実習生数、"
        "就労予定期間、入社日、月額給与、実務経験月数、役職、職種、"
        "活動内容詳細を抽出してください。"
    ),
    "education": (
        "以下の書類から学歴・専攻・資格情報を抽出してください。"
        "最終学歴区分、学校名、卒業年月日、専攻・専門分野、"
        "情報処理技術者資格の有無と資格名を抽出してください。"
    ),
    "review": (
        "以下の抽出済みデータと原本書類を照合し、レビューしてください。"
    ),
}

_SCOPED_COMMON_RULES = """\
## 出力形式

各フィールドは `{"value": "...", "source": "document_id|page|text_quote|confidence"}` の形式で出力すること。

### source フォーマット
- document_id: 書類一覧の document_id と一致
- page: ページ番号（1始まり）
- text_quote: 原文から直接引用、50文字以内。パイプ文字(|)は含めない
- confidence: 0.0〜1.0（0.9以上=明瞭、0.7-0.9=やや不明瞭、0.5-0.7=複数解釈可能、0.5未満=推測）
- 値が見つからない場合は value を空文字、source を空文字とすること

### 正規化ルール
- 法人番号（`employer.corporate_number`）: 13桁の数字のみ。ハイフン・スペースは除去すること。
- DOCX書類からの抽出: ページ概念がないため page は 1 とすること。

### 出力言語ルール
- 値は原本の言語をそのまま使用（例：ローマ字氏名はローマ字、日本語住所は日本語）
- 説明テキスト（reason, message 等）は日本語で記述
- text_quote は原文から直接引用

### 証跡必須ルール
- 値を出力する場合は、必ず source も出力すること。証跡なしで値だけ返すことは禁止。
- 値が "無" や "No" など否定的な内容であっても、書類に記載されているなら source を付けること。

正しい出力例:
```json
{
  "criminal_record": {
    "value": "無",
    "source": "doc_xyz789|1|犯罪を理由とする処分を受けたことの有無 無|0.95"
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


def build_scoped_prompt(
    scope: str,
    case_meta: dict,
    documents: list[dict],
    extra_context: dict | None = None,
) -> str:
    """Build a scope-specific extraction prompt.

    Args:
        scope: One of "identity", "employer", "education", "review".
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
        document_descriptions=doc_text,
    )
