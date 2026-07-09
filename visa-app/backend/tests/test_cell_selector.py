"""cell_selector のユニットテスト。Gemini はモックで置き換え。"""

from unittest.mock import patch

from extractors.cell_selector import select_ambiguous_cells


def _ambiguous_ref(quote: str, candidates: list[dict]) -> dict:
    return {
        "document_id": "doc_xlsx",
        "page": 5,
        "text_quote": quote,
        "confidence": 0.9,
        "anchor": {
            "type": "xlsx_cell",
            "status": "ambiguous",
            "resolver_type": "xlsx_cell_index",
            "match_count": len(candidates),
            "candidates": candidates,
        },
    }


def _candidate(sheet: str, cell: str, row: int) -> dict:
    return {"anchor_id": f"{sheet}!{cell}", "sheet_name": sheet, "cell": cell, "row": row, "col": 4}


_XLSX_INDEX = {
    "doc_xlsx": [
        {"sheet_name": "Bhawana", "cell": "C11", "row": 11, "col": 3, "text": "過去に来日したことはありますか"},
        {"sheet_name": "Bhawana", "cell": "D11", "row": 11, "col": 4, "text": "No"},
        {"sheet_name": "Bhawana", "cell": "C14", "row": 14, "col": 3, "text": "犯罪歴はありますか"},
        {"sheet_name": "Bhawana", "cell": "D14", "row": 14, "col": 4, "text": "No"},
    ]
}


def test_select_resolves_with_valid_pick_and_keeps_candidates():
    candidates = [_candidate("Bhawana", "D11", 11), _candidate("Bhawana", "D14", 14)]
    field_metadata = {
        "applicant.immigration_history.criminal_record": {
            "source_refs": [_ambiguous_ref("No", candidates)]
        }
    }

    def fake_select(context_text, selections):
        assert "犯罪歴はありますか" in context_text
        (selection_id, selection), = selections.items()
        assert selection["field_path"] == "applicant.immigration_history.criminal_record"
        assert selection["candidate_anchor_ids"] == ["Bhawana!D11", "Bhawana!D14"]
        return {selection_id: {"anchor_id": "Bhawana!D14", "reason": "犯罪歴の行"}}

    with patch("extractors.cell_selector.select_anchor_cells", side_effect=fake_select):
        result = select_ambiguous_cells(field_metadata, _XLSX_INDEX)

    anchor = result["applicant.immigration_history.criminal_record"]["source_refs"][0]["anchor"]
    assert anchor["status"] == "resolved"
    assert anchor["resolver_type"] == "gemini_cell_select"
    assert anchor["anchor_id"] == "Bhawana!D14"
    assert anchor["sheet_name"] == "Bhawana"
    assert anchor["cell"] == "D14"
    assert anchor["select_reason"] == "犯罪歴の行"
    assert len(anchor["candidates"]) == 2


def test_select_rejects_anchor_id_outside_candidates():
    candidates = [_candidate("Bhawana", "D11", 11), _candidate("Bhawana", "D14", 14)]
    field_metadata = {
        "applicant.immigration_history.criminal_record": {
            "source_refs": [_ambiguous_ref("No", candidates)]
        }
    }

    def fake_select(_context, selections):
        (selection_id,) = selections
        return {selection_id: {"anchor_id": "Bhawana!Z99", "reason": "hallucination"}}

    with patch("extractors.cell_selector.select_anchor_cells", side_effect=fake_select):
        result = select_ambiguous_cells(field_metadata, _XLSX_INDEX)

    anchor = result["applicant.immigration_history.criminal_record"]["source_refs"][0]["anchor"]
    assert anchor["status"] == "ambiguous"


def test_select_null_keeps_ambiguous():
    candidates = [_candidate("Bhawana", "D11", 11), _candidate("Bhawana", "D14", 14)]
    field_metadata = {
        "applicant.immigration_history.criminal_record": {
            "source_refs": [_ambiguous_ref("No", candidates)]
        }
    }

    with patch(
        "extractors.cell_selector.select_anchor_cells",
        return_value={"selection_0000": None},
    ):
        result = select_ambiguous_cells(field_metadata, _XLSX_INDEX)

    anchor = result["applicant.immigration_history.criminal_record"]["source_refs"][0]["anchor"]
    assert anchor["status"] == "ambiguous"


def _resolved_xlsx_ref(sheet: str) -> dict:
    return {
        "document_id": "doc_xlsx",
        "text_quote": "PA9999999",
        "anchor": {
            "type": "xlsx_cell",
            "status": "resolved",
            "resolver_type": "xlsx_cell_index",
            "sheet_name": sheet,
            "anchor_id": f"{sheet}!D7",
        },
    }


def test_select_skips_candidates_off_preferred_sheet():
    """申請人シート上に候補がない場合は、他人のセルを選ばせず保留する。"""
    field_metadata = {
        "applicant.passport.number": {"source_refs": [_resolved_xlsx_ref("Bhawana")]},
        "applicant.has_employment_history": {
            "source_refs": [
                _ambiguous_ref(
                    "NA",
                    [_candidate("Manoj", "E6", 6), _candidate("Amit", "E6", 6)],
                )
            ]
        },
    }

    with patch("extractors.cell_selector.select_anchor_cells") as mock_select:
        result = select_ambiguous_cells(field_metadata, _XLSX_INDEX)

    mock_select.assert_not_called()
    anchor = result["applicant.has_employment_history"]["source_refs"][0]["anchor"]
    assert anchor["status"] == "ambiguous"


def test_select_restricts_candidates_to_preferred_sheet():
    """他人シートの候補が混ざっていても、申請人シートの候補だけをGeminiに渡す。"""
    field_metadata = {
        "applicant.passport.number": {"source_refs": [_resolved_xlsx_ref("Bhawana")]},
        "applicant.immigration_history.criminal_record": {
            "source_refs": [
                _ambiguous_ref(
                    "No",
                    [
                        _candidate("Bhawana", "D11", 11),
                        _candidate("Bhawana", "D14", 14),
                        _candidate("Manoj", "D14", 14),
                    ],
                )
            ]
        },
    }

    def fake_select(_context, selections):
        (selection_id, selection), = selections.items()
        assert selection["candidate_anchor_ids"] == ["Bhawana!D11", "Bhawana!D14"]
        return {selection_id: {"anchor_id": "Bhawana!D14", "reason": "犯罪歴の行"}}

    with patch("extractors.cell_selector.select_anchor_cells", side_effect=fake_select):
        result = select_ambiguous_cells(field_metadata, _XLSX_INDEX)

    anchor = result["applicant.immigration_history.criminal_record"]["source_refs"][0]["anchor"]
    assert anchor["status"] == "resolved"
    assert anchor["anchor_id"] == "Bhawana!D14"


def test_select_skips_when_no_ambiguous_xlsx():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "text_quote": "TARO",
                    "anchor": {"type": "pdf_bbox", "status": "resolved"},
                }
            ]
        }
    }

    with patch("extractors.cell_selector.select_anchor_cells") as mock_select:
        select_ambiguous_cells(field_metadata, _XLSX_INDEX)

    mock_select.assert_not_called()


def test_select_survives_gemini_failure():
    candidates = [_candidate("Bhawana", "D11", 11), _candidate("Bhawana", "D14", 14)]
    field_metadata = {
        "applicant.immigration_history.criminal_record": {
            "source_refs": [_ambiguous_ref("No", candidates)]
        }
    }

    with patch(
        "extractors.cell_selector.select_anchor_cells",
        side_effect=RuntimeError("api down"),
    ):
        result = select_ambiguous_cells(field_metadata, _XLSX_INDEX)

    anchor = result["applicant.immigration_history.criminal_record"]["source_refs"][0]["anchor"]
    assert anchor["status"] == "ambiguous"
