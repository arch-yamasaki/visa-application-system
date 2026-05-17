"""Local extraction test using desktop files with Gemini 3 Flash."""

import json
import os
import sys
from pathlib import Path

# Set API key before imports
os.environ["GOOGLE_API_KEY"] = "AIzaSyBDsK0vJkm4rwwsdHsg2pBAxDAeRPziNCc"

# Add parent to path for extractors import
sys.path.insert(0, str(Path(__file__).parent))

from extractors.gemini import extract_pdf_direct, extract_text_only
from extractors.pdf_text import has_text_layer, extract_text
from extractors.vision import ocr_document
from extractors.xlsx import extract_xlsx
from extractors.docx_text import extract_docx

INPUT_DIR = Path.home() / "Desktop" / "visa-test-amit_tamang"
OUTPUT_DIR = INPUT_DIR / "output"

CASE_META = {
    "case_id": "test-amit-tamang",
    "application_type": "certificate_of_eligibility",
    "target_status": "engineer_humanities_international",
}


def load_files():
    """Load all input files from desktop folder."""
    files = []
    for f in sorted(INPUT_DIR.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "document_id": f"doc_{len(files)+1:03d}",
                "file_name": f.name,
                "document_role": guess_role(f.name),
                "path": f,
                "bytes": f.read_bytes(),
            })
    return files


def guess_role(name: str) -> str:
    lower = name.lower()
    if "オファー" in lower or "offer" in lower:
        return "employment_terms"
    if "会社" in lower or "company" in lower:
        return "company_documents"
    if "coe" in lower or "内定" in lower:
        return "intake_spreadsheet"
    return "other"


def run_pattern_b(files):
    """Pattern B: PDF direct to Gemini (+ xlsx/docx as text)."""
    print("\n=== Pattern B: PDF直接入力（全書類対応） ===")
    pdf_contents = []
    text_contents = []
    documents = []
    for f in files:
        ext = f["path"].suffix.lower()
        if ext == ".pdf":
            pdf_contents.append((f["document_id"], f["bytes"]))
        elif ext in (".xlsx", ".xls"):
            ocr = extract_xlsx(f["bytes"], f["document_id"])
            text_contents.append((f["document_id"], "\n".join(p.text for p in ocr.pages)))
        elif ext in (".docx", ".doc"):
            ocr = extract_docx(f["bytes"], f["document_id"])
            text_contents.append((f["document_id"], "\n".join(p.text for p in ocr.pages)))
        documents.append({
            "document_id": f["document_id"],
            "file_name": f["file_name"],
            "document_role": f["document_role"],
        })

    if not pdf_contents and not text_contents:
        print("対応ファイルがありません")
        return None

    print(f"PDFファイル数: {len(pdf_contents)}")
    print(f"テキスト抽出ファイル数: {len(text_contents)}")
    print(f"全ファイル数: {len(documents)}")
    print("Gemini 3 Flash に送信中...")

    result = extract_pdf_direct(pdf_contents, CASE_META, documents, text_contents=text_contents or None)
    return result


def run_pattern_a(files):
    """Pattern A: OCR text only."""
    print("\n=== Pattern A: OCRテキストのみ ===")
    ocr_results = []
    documents = []
    for f in files:
        ext = f["path"].suffix.lower()
        if ext in (".pdf", ".png", ".jpg", ".jpeg"):
            print(f"  OCR中: {f['file_name']}...")
            ocr = ocr_document(f["bytes"], f["file_name"], f["document_id"])
            ocr_results.append(ocr)
            for p in ocr.pages:
                print(f"    p.{p.page_number}: {len(p.text)} chars, {len(p.words)} words")
        documents.append({
            "document_id": f["document_id"],
            "file_name": f["file_name"],
            "document_role": f["document_role"],
        })

    print(f"OCR結果: {len(ocr_results)} files")
    print("Gemini 3 Flash に送信中...")

    result = extract_text_only(ocr_results, CASE_META, documents)
    return result


def save_result(result, pattern_name):
    OUTPUT_DIR.mkdir(exist_ok=True)
    prefix = OUTPUT_DIR / pattern_name

    with open(f"{prefix}_case_data.json", "w") as f:
        json.dump(result.case_data, f, ensure_ascii=False, indent=2)
    with open(f"{prefix}_review.json", "w") as f:
        json.dump(result.review, f, ensure_ascii=False, indent=2)
    with open(f"{prefix}_field_metadata.json", "w") as f:
        json.dump(result.field_metadata, f, ensure_ascii=False, indent=2)

    print(f"\n出力先: {OUTPUT_DIR}/")
    print(f"  {pattern_name}_case_data.json")
    print(f"  {pattern_name}_review.json")
    print(f"  {pattern_name}_field_metadata.json")


def show_summary(result):
    cd = result.case_data
    applicant = cd.get("applicant", {})
    print(f"\n--- 抽出結果サマリー ---")
    print(f"氏名: {applicant.get('name_roman', '?')}")
    print(f"国籍: {applicant.get('nationality_region', '?')}")
    print(f"生年月日: {applicant.get('birth_date', '?')}")
    print(f"雇用主: {cd.get('employer', {}).get('name', '?')}")
    print(f"活動内容: {cd.get('application', {}).get('activity_details', '?')[:80]}...")

    review = result.review
    print(f"\nレビュー: {review.get('expected_route', '?')}")
    print(f"欠損項目: {len(review.get('missing_items', []))} 件")
    print(f"所見: {len(review.get('findings', []))} 件")
    print(f"field_metadata: {len(result.field_metadata)} fields")


if __name__ == "__main__":
    print(f"入力フォルダ: {INPUT_DIR}")
    files = load_files()
    print(f"ファイル数: {len(files)}")
    for f in files:
        print(f"  {f['document_id']}: {f['file_name']} ({f['document_role']})")

    # Pattern B (PDF直接) を実行
    result = run_pattern_b(files)
    if result:
        show_summary(result)
        save_result(result, "pattern_b")
