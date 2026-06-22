"""anchor_resolver のユニットテスト。"""

import pymupdf

from extractors.anchor_resolver import resolve_anchors, sync_bbox_anchors


def _pdf_with_text(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    y = 40
    for line in lines:
        page.insert_text((40, y), line, fontsize=12)
        y += 30
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_resolve_anchors_adds_pdf_text_layer_bbox():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": _pdf_with_text(["AMIT TAMANG"])})
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["resolver_type"] == "pdf_text_layer"
    assert ref["anchor"]["bbox"] == ref["bbox"]
    assert ref["bbox"]["x_min"] < ref["bbox"]["x_max"]
    assert ref["bbox"]["y_min"] < ref["bbox"]["y_max"]


def test_resolve_anchors_marks_duplicate_pdf_text_as_ambiguous():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(
        field_metadata,
        {"doc_pdf": _pdf_with_text(["基本給 260000", "月額合計 260000"])},
    )
    ref = result["employment.monthly_salary"]["source_refs"][0]

    assert "bbox" not in ref
    assert ref["anchor"] == {
        "type": "pdf_bbox",
        "status": "ambiguous",
        "resolver_type": "pdf_text_layer",
        "match_count": 2,
    }


def test_sync_bbox_anchors_preserves_legacy_bbox():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                    "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                }
            ]
        }
    }

    result = sync_bbox_anchors(field_metadata)
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "pdf_bbox",
        "status": "resolved",
        "resolver_type": "gemini_bbox",
        "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
        "match_count": 1,
    }


def test_resolve_anchors_adds_xlsx_cell_anchor():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                }
            ]
        }
    }
    xlsx_index = {
        "doc_xlsx": [
            {
                "type": "xlsx_cell",
                "sheet_name": "Sheet1",
                "cell": "B2",
                "row": 2,
                "col": 2,
                "text": "260000",
                "anchor_id": "Sheet1!B2",
            }
        ]
    }

    result = resolve_anchors(field_metadata, {}, xlsx_index, {})
    ref = result["employment.monthly_salary"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "xlsx_cell",
        "status": "resolved",
        "resolver_type": "xlsx_cell_index",
        "match_count": 1,
        "anchor_id": "Sheet1!B2",
        "sheet_name": "Sheet1",
        "cell": "B2",
        "row": 2,
        "col": 2,
    }


def test_resolve_anchors_marks_duplicate_docx_blocks_as_ambiguous():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_docx",
                    "page": 1,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        }
    }
    docx_index = {
        "doc_docx": [
            {"type": "docx_block", "paragraph_index": 0, "text": "AMIT TAMANG", "anchor_id": "p-0"},
            {"type": "docx_block", "paragraph_index": 1, "text": "Applicant AMIT TAMANG", "anchor_id": "p-1"},
        ]
    }

    result = resolve_anchors(field_metadata, {}, {}, docx_index)
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "docx_block",
        "status": "ambiguous",
        "resolver_type": "docx_block_index",
        "match_count": 2,
    }
