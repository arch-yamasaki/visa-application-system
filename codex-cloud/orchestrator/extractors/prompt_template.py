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

提供された書類から以下の3つのJSONオブジェクトを含む単一のJSONを出力してください。

1. **case_data**: 申請人の身元情報、出入国歴、家族、学歴、職歴、資格、雇用主情報、雇用条件、活動内容詳細を抽出。
2. **review**: 欠損項目、根拠の弱い項目、矛盾点、人の判断が必要な理由を記録。reason/message/summaryは日本語で記述。
3. **field_metadata**: 各フィールドの抽出根拠を記録。

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
- field_metadata: text_quoteは原文から直接引用

## レビュー方針（技人国）

- 職務内容が学歴・専攻・職歴・成績科目とつながっているか
- 職務内容が単純労働に見えないか
- 活動内容詳細が具体的か
- 書類の欠損や矛盾がないか

根拠となる資料が不足している場合、OCR精度が低い場合、法的・実務的な判断が必要な場合は needs_review を付与すること。

## field_metadata 要件

各フィールドパスに対して source_refs を記録する。
- field_path は case_data のドットパス表記（例: applicant.name_roman, education.0.school_name）
- text_quote は原文から直接引用し50文字以内
- confidence: 0.9以上=明瞭、0.7-0.9=やや不明瞭、0.5-0.7=複数解釈可能、0.5未満=推測
- 値が見つからない場合は source_refs を空配列とし review の missing_items に記録

## 出力フォーマット

値が見つからない場合は空文字またはnullとすること。
"""


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
