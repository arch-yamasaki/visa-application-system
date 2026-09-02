"""anchor_resolver unit tests."""

import pymupdf

from extractors.anchor_resolver import anchor_coverage, resolve_source_locations, sync_bbox_anchors


def _pdf_with_pages(page_count: int) -> bytes:
    doc = pymupdf.open()
    for _ in range(page_count):
        doc.new_page(width=300, height=200)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _xlsx_cell(sheet: str, cell: str, row: int, col: int, text: str) -> dict:
    return {
        "type": "xlsx_cell",
        "sheet_name": sheet,
        "cell": cell,
        "row": row,
        "col": col,
        "text": text,
        "anchor_id": f"{sheet}!{cell}",
    }


def test_resolves_explicit_xlsx_location_without_text_match():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 1,
                    "text_quote": "different quote",
                    "confidence": 0.9,
                    "locations": [{"type": "xlsx_cell", "anchor_id": "Applicant!B2"}],
                }
            ]
        }
    }
    xlsx_index = {"doc_xlsx": [_xlsx_cell("Applicant", "B2", 2, 2, "260000")]}

    result = resolve_source_locations(field_metadata, {}, xlsx_index, {})
    anchor = result["employment.monthly_salary"]["source_refs"][0]["anchor"]

    assert anchor == {
        "type": "xlsx_cell",
        "status": "resolved",
        "resolver_type": "source_ref_location",
        "match_count": 1,
        "anchor_id": "Applicant!B2",
        "sheet_name": "Applicant",
        "cell": "B2",
        "row": 2,
        "col": 2,
    }


def test_invalid_explicit_xlsx_location_does_not_fallback_to_quote_match():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                    "locations": [{"type": "xlsx_cell", "anchor_id": "Applicant!Z9"}],
                }
            ]
        }
    }
    xlsx_index = {"doc_xlsx": [_xlsx_cell("Applicant", "B2", 2, 2, "260000")]}

    result = resolve_source_locations(field_metadata, {}, xlsx_index, {})
    anchor = result["employment.monthly_salary"]["source_refs"][0]["anchor"]

    assert anchor == {
        "type": "source_location",
        "status": "not_found",
        "resolver_type": "source_ref_location",
        "match_count": 0,
    }


def test_legacy_ref_without_locations_is_left_unchanged():
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
    xlsx_index = {"doc_xlsx": [_xlsx_cell("Applicant", "B2", 2, 2, "260000")]}

    result = resolve_source_locations(field_metadata, {}, xlsx_index, {})
    ref = result["employment.monthly_salary"]["source_refs"][0]

    assert "anchor" not in ref


def test_legacy_existing_anchor_is_preserved():
    existing_anchor = {
        "type": "xlsx_cell",
        "status": "resolved",
        "anchor_id": "Applicant!B2",
    }
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                    "anchor": existing_anchor,
                }
            ]
        }
    }

    result = resolve_source_locations(field_metadata, {}, {}, {})

    assert result["employment.monthly_salary"]["source_refs"][0]["anchor"] is existing_anchor


def test_resolves_explicit_docx_location():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_docx",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.9,
                    "locations": [{"type": "docx_block", "anchor_id": "p-0"}],
                }
            ]
        }
    }
    docx_index = {
        "doc_docx": [
            {
                "type": "docx_block",
                "block_kind": "paragraph",
                "paragraph_index": 0,
                "text": "TANAKA TARO",
                "anchor_id": "p-0",
            }
        ]
    }

    result = resolve_source_locations(field_metadata, {}, {}, docx_index)
    anchor = result["applicant.name_roman"]["source_refs"][0]["anchor"]

    assert anchor["status"] == "resolved"
    assert anchor["anchor_id"] == "p-0"
    assert anchor["paragraph_index"] == 0


def test_resolves_explicit_pdf_bbox_location():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.9,
                    "locations": [
                        {
                            "type": "pdf_bbox",
                            "page": 2,
                            "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                        }
                    ],
                }
            ]
        }
    }

    result = resolve_source_locations(field_metadata, {"doc_pdf": _pdf_with_pages(2)})
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["bbox"] == {"y_min": 100.0, "x_min": 200.0, "y_max": 130.0, "x_max": 260.0}
    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["page"] == 2


def test_rejects_pdf_bbox_outside_page_or_coordinate_bounds():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.9,
                    "locations": [
                        {
                            "type": "pdf_bbox",
                            "page": 2,
                            "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 1001},
                        },
                        {
                            "type": "pdf_bbox",
                            "page": 3,
                            "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                        },
                    ],
                }
            ]
        }
    }

    result = resolve_source_locations(field_metadata, {"doc_pdf": _pdf_with_pages(2)})
    anchor = result["applicant.name_roman"]["source_refs"][0]["anchor"]

    assert anchor["status"] == "not_found"


def test_invalid_explicit_pdf_location_drops_stale_bbox_without_fallback():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.9,
                    "bbox": {"y_min": 10, "x_min": 10, "y_max": 20, "x_max": 20},
                    "locations": [
                        {
                            "type": "pdf_bbox",
                            "page": 0,
                            "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                        }
                    ],
                }
            ]
        }
    }

    result = resolve_source_locations(field_metadata, {"doc_pdf": _pdf_with_pages(1)})
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert "bbox" not in ref
    assert ref["anchor"]["status"] == "not_found"


def test_rejects_non_finite_pdf_bbox():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.9,
                    "locations": [
                        {
                            "type": "pdf_bbox",
                            "page": 1,
                            "bbox": {"y_min": float("nan"), "x_min": 200, "y_max": 130, "x_max": 260},
                        }
                    ],
                }
            ]
        }
    }

    result = resolve_source_locations(field_metadata, {"doc_pdf": _pdf_with_pages(1)})

    assert result["applicant.name_roman"]["source_refs"][0]["anchor"]["status"] == "not_found"


def test_multiple_explicit_locations_are_kept_as_candidates():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_docx",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.9,
                    "locations": [
                        {"type": "docx_block", "anchor_id": "p-0"},
                        {"type": "docx_block", "anchor_id": "p-1"},
                    ],
                }
            ]
        }
    }
    docx_index = {
        "doc_docx": [
            {"type": "docx_block", "paragraph_index": 0, "text": "TANAKA TARO", "anchor_id": "p-0"},
            {"type": "docx_block", "paragraph_index": 1, "text": "TANAKA TARO", "anchor_id": "p-1"},
        ]
    }

    result = resolve_source_locations(field_metadata, {}, {}, docx_index)
    anchor = result["applicant.name_roman"]["source_refs"][0]["anchor"]

    assert anchor == {
        "type": "docx_block",
        "status": "ambiguous",
        "resolver_type": "source_ref_location",
        "match_count": 2,
        "candidates": [
            {"anchor_id": "p-0", "paragraph_index": 0},
            {"anchor_id": "p-1", "paragraph_index": 1},
        ],
    }


def test_alternative_source_location_is_resolved():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [],
            "alternatives": [
                {
                    "value": "230000",
                    "origin": "document",
                    "source_refs": [
                        {
                            "document_id": "doc_xlsx",
                            "page": 1,
                            "text_quote": "230000",
                            "confidence": 0.8,
                            "locations": [
                                {"type": "xlsx_cell", "anchor_id": "Applicant!B3"}
                            ],
                        }
                    ],
                }
            ],
        }
    }
    xlsx_index = {"doc_xlsx": [_xlsx_cell("Applicant", "B3", 3, 2, "230000")]}

    result = resolve_source_locations(field_metadata, {}, xlsx_index, {})
    ref = result["employment.monthly_salary"]["alternatives"][0]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["anchor_id"] == "Applicant!B3"


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
        "resolver_type": "existing_bbox",
        "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
        "match_count": 1,
        "page": 1,
    }


def test_anchor_coverage_counts_resolved_candidates_and_unresolved():
    field_metadata = {
        "a.resolved": {
            "source_refs": [
                {"document_id": "d1", "text_quote": "x", "anchor": {"status": "resolved"}}
            ]
        },
        "a.candidates": {
            "source_refs": [
                {
                    "document_id": "d1",
                    "text_quote": "y",
                    "anchor": {
                        "status": "ambiguous",
                        "candidates": [{"anchor_id": "Sheet1!B2"}],
                    },
                }
            ]
        },
        "a.not_found": {
            "source_refs": [
                {"document_id": "d1", "text_quote": "z", "anchor": {"status": "not_found"}}
            ]
        },
        "a.no_evidence": {
            "source_refs": [{"document_id": "", "text_quote": ""}]
        },
    }

    coverage = anchor_coverage(field_metadata)

    assert coverage == {
        "total_fields": 3,
        "resolved_fields": 1,
        "displayable_fields": 2,
    }


def test_anchor_coverage_counts_only_document_fields_with_values():
    field_metadata = {
        "a.document": {"origin": "document", "has_value": True, "source_refs": []},
        "a.empty": {"origin": "document", "has_value": False, "source_refs": []},
        "a.derived": {"origin": "derived", "has_value": True, "source_refs": []},
        "a.setting": {"origin": "setting", "has_value": True, "source_refs": []},
    }

    assert anchor_coverage(field_metadata) == {
        "total_fields": 1,
        "resolved_fields": 0,
        "displayable_fields": 0,
    }
