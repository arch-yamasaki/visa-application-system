"""bbox_locator のユニットテスト。Gemini API はモックで置き換え。"""

from unittest.mock import MagicMock, patch

from extractors.bbox_locator import locate_bboxes


def _fake_pdf_doc():
    pix = MagicMock()
    pix.tobytes.return_value = b"png"
    page = MagicMock()
    page.get_pixmap.return_value = pix
    doc = MagicMock()
    doc.__len__.return_value = 1
    doc.__getitem__.return_value = page
    return doc


def test_locate_bboxes_assigns_bbox_to_matching_ref_index():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "FIRST",
                    "confidence": 0.9,
                },
                {
                    "document_id": "doc_pdf",
                    "page": "1",
                    "text_quote": "SECOND",
                    "confidence": 0.9,
                },
            ]
        }
    }

    def fake_get_bboxes(_image_bytes, candidates):
        second_id = [
            candidate_id
            for candidate_id, candidate in candidates.items()
            if candidate["text_quote"] == "SECOND"
        ][0]
        return {second_id: [100, 200, 130, 260]}

    with patch("extractors.bbox_locator.pymupdf.open", return_value=_fake_pdf_doc()):
        with patch("extractors.bbox_locator.get_bboxes_for_page", side_effect=fake_get_bboxes):
            result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    refs = result["applicant.name_roman"]["source_refs"]
    assert "bbox" not in refs[0]
    assert refs[1]["bbox"] == {
        "y_min": 100,
        "x_min": 200,
        "y_max": 130,
        "x_max": 260,
    }


def test_locate_bboxes_assigns_bbox_to_alternative_ref():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "PRIMARY",
                    "confidence": 0.9,
                    "anchor": {
                        "type": "pdf_bbox",
                        "status": "resolved",
                        "resolver_type": "pdf_text_layer",
                        "match_count": 1,
                    },
                }
            ],
            "alternatives": [
                {
                    "value": "ALT",
                    "source_refs": [
                        {
                            "document_id": "doc_pdf",
                            "page": "1",
                            "text_quote": "ALT",
                            "confidence": 0.8,
                        }
                    ],
                }
            ],
        }
    }

    def fake_get_bboxes(_image_bytes, candidates):
        candidate_id = next(iter(candidates))
        assert candidates[candidate_id]["text_quote"] == "ALT"
        return {candidate_id: [100, 200, 130, 260]}

    with patch("extractors.bbox_locator.pymupdf.open", return_value=_fake_pdf_doc()):
        with patch("extractors.bbox_locator.get_bboxes_for_page", side_effect=fake_get_bboxes):
            result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    primary_ref = result["applicant.name_roman"]["source_refs"][0]
    alt_ref = result["applicant.name_roman"]["alternatives"][0]["source_refs"][0]
    assert "bbox" not in primary_ref
    assert alt_ref["bbox"] == {
        "y_min": 100,
        "x_min": 200,
        "y_max": 130,
        "x_max": 260,
    }


def test_locate_bboxes_includes_employment_insurance_office_number():
    field_metadata = {
        "employer.employment_insurance_office_number": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "1301-010392-4",
                    "confidence": 0.9,
                }
            ]
        }
    }

    def fake_get_bboxes(_image_bytes, candidates):
        candidate_id = next(iter(candidates))
        assert candidates[candidate_id]["field_path"] == "employer.employment_insurance_office_number"
        return {candidate_id: [100, 200, 130, 260]}

    with patch("extractors.bbox_locator.pymupdf.open", return_value=_fake_pdf_doc()):
        with patch("extractors.bbox_locator.get_bboxes_for_page", side_effect=fake_get_bboxes):
            result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    ref = result["employer.employment_insurance_office_number"]["source_refs"][0]
    assert ref["bbox"] == {
        "y_min": 100,
        "x_min": 200,
        "y_max": 130,
        "x_max": 260,
    }


def test_locate_bboxes_includes_employment_history_and_education_by_prefix():
    field_metadata = {
        "applicant.employment_history.1.company_name_en": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "KATHMANDU RESTAURANT (CHENGDU)",
                    "confidence": 0.9,
                    "anchor": {
                        "type": "pdf_bbox",
                        "status": "not_found",
                        "resolver_type": "pdf_text_layer",
                        "match_count": 0,
                    },
                }
            ]
        },
        "applicant.education.1.school_name": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "SICHUAN UNIVERSITY",
                    "confidence": 0.9,
                }
            ]
        },
    }

    def fake_get_bboxes(_image_bytes, candidates):
        assert {candidate["field_path"] for candidate in candidates.values()} == {
            "applicant.employment_history.1.company_name_en",
            "applicant.education.1.school_name",
        }
        return {candidate_id: [100, 200, 130, 260] for candidate_id in candidates}

    with patch("extractors.bbox_locator.pymupdf.open", return_value=_fake_pdf_doc()):
        with patch("extractors.bbox_locator.get_bboxes_for_page", side_effect=fake_get_bboxes):
            result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    expected = {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260}
    assert result["applicant.employment_history.1.company_name_en"]["source_refs"][0]["bbox"] == expected
    assert result["applicant.education.1.school_name"]["source_refs"][0]["bbox"] == expected


def test_locate_bboxes_skips_low_quality_quotes():
    field_metadata = {
        "applicant.employment_history.0.start_month_unknown": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "true",
                    "confidence": 0.9,
                }
            ]
        },
        "applicant.employment_history.0.country_region": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "X",
                    "confidence": 0.9,
                }
            ]
        },
    }

    with patch("extractors.bbox_locator.get_bboxes_for_page") as mock_get_bboxes:
        result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    mock_get_bboxes.assert_not_called()
    for meta in result.values():
        assert "bbox" not in meta["source_refs"][0]


def test_locate_bboxes_dedupes_same_locator_and_applies_to_all_refs():
    field_metadata = {
        "applicant.employment_history.0.company_name_en": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "KATHMANDU RESTAURANT (CHENGDU)",
                    "confidence": 0.9,
                }
            ]
        },
        "applicant.employment_history.0.company_name_local": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "KATHMANDU RESTAURANT (CHENGDU)",
                    "confidence": 0.9,
                }
            ]
        },
    }

    def fake_get_bboxes(_image_bytes, candidates):
        assert len(candidates) == 1
        return {next(iter(candidates)): [100, 200, 130, 260]}

    with patch("extractors.bbox_locator.pymupdf.open", return_value=_fake_pdf_doc()):
        with patch("extractors.bbox_locator.get_bboxes_for_page", side_effect=fake_get_bboxes):
            result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    expected = {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260}
    assert result["applicant.employment_history.0.company_name_en"]["source_refs"][0]["bbox"] == expected
    assert result["applicant.employment_history.0.company_name_local"]["source_refs"][0]["bbox"] == expected


def test_locate_bboxes_skips_ambiguous_anchor():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                    "anchor": {
                        "type": "pdf_bbox",
                        "status": "ambiguous",
                        "resolver_type": "pdf_text_layer",
                        "match_count": 2,
                    },
                }
            ]
        }
    }

    with patch("extractors.bbox_locator.get_bboxes_for_page") as mock_get_bboxes:
        result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    mock_get_bboxes.assert_not_called()
    ref = result["employment.monthly_salary"]["source_refs"][0]
    assert "bbox" not in ref
    assert ref["anchor"]["status"] == "ambiguous"


def test_locate_bboxes_skips_non_pdf_refs():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_docx",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.9,
                }
            ]
        }
    }

    with patch("extractors.bbox_locator.get_bboxes_for_page") as mock_get_bboxes:
        result = locate_bboxes(field_metadata, {"doc_pdf": b"pdf"})

    mock_get_bboxes.assert_not_called()
    assert "bbox" not in result["applicant.name_roman"]["source_refs"][0]
