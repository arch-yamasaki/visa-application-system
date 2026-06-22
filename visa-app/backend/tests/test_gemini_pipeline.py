"""gemini_pipeline anchor post-processing tests."""

from extractors.document_models import PreparedDocuments
from extractors.gemini_pipeline import attach_bboxes
from extractors.types import ExtractionResult


def test_attach_bboxes_resolves_office_anchors_without_pdfs():
    result = ExtractionResult(
        case_data={},
        display_case_data={},
        review={},
        field_metadata={
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
        },
    )
    prepared = PreparedDocuments(
        xlsx_cell_indexes={
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
    )

    updated = attach_bboxes(result, prepared, case_id="case_test")
    ref = updated.field_metadata["employment.monthly_salary"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["type"] == "xlsx_cell"
    assert ref["anchor"]["cell"] == "B2"


def test_attach_bboxes_keeps_deterministic_anchors_when_bbox_locator_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_BBOX_LOCATOR", "false")
    result = ExtractionResult(
        case_data={},
        display_case_data={},
        review={},
        field_metadata={
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
        },
    )
    prepared = PreparedDocuments(
        pdf_contents=[("doc_pdf", b"pdf")],
        pdf_bytes_map={"doc_pdf": b"pdf"},
        docx_block_indexes={
            "doc_docx": [
                {
                    "type": "docx_block",
                    "block_kind": "paragraph",
                    "paragraph_index": 0,
                    "text": "AMIT TAMANG",
                    "anchor_id": "p-0",
                }
            ]
        },
    )

    updated = attach_bboxes(result, prepared, case_id="case_test")
    ref = updated.field_metadata["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["type"] == "docx_block"
    assert ref["anchor"]["paragraph_index"] == 0
