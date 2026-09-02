"""Document helper tests for main API module."""

import io

import openpyxl
import pytest
from fastapi import HTTPException

from main import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    _file_extension,
    _format_extraction_error,
    _merge_extracted_case_data,
    _merge_extracted_field_metadata,
    _xlsx_to_html,
)


def test_supported_document_extensions_match_safe_preview_formats():
    assert SUPPORTED_DOCUMENT_EXTENSIONS == {"pdf", "docx", "xlsx", "png", "jpg", "jpeg"}


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("offer.DOCX", "docx"),
        ("sheet.xlsx", "xlsx"),
        ("no_extension", ""),
    ],
)
def test_file_extension(file_name, expected):
    assert _file_extension(file_name) == expected


def test_xlsx_to_html_rejects_unknown_sheet():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Applicants"
    ws["A1"] = "Name"
    buffer = io.BytesIO()
    wb.save(buffer)
    wb.close()

    with pytest.raises(HTTPException) as exc:
        _xlsx_to_html(buffer.getvalue(), sheet_name="Missing")

    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Gemini API key is invalid or not permitted. Check GOOGLE_API_KEY.",
            "Gemini APIキーが無効、または権限不足です。GOOGLE_API_KEYを確認してください。",
        ),
        (
            "Gemini API quota was exhausted.",
            "API利用上限に達しました。しばらく待ってから再度お試しください。",
        ),
    ],
)
def test_format_extraction_error_handles_scoped_gemini_messages(message, expected):
    assert _format_extraction_error(RuntimeError(message)) == expected


def test_reextraction_preserves_human_edited_passport_identity_fields():
    existing = {
        "applicant": {
            "name_roman": "HUMAN CONFIRMED",
            "birth_date": "1990-01-02",
            "sex": "male",
        }
    }
    extracted = {
        "applicant": {
            "name_roman": "MODEL VALUE",
            "birth_date": "",
            "sex": "female",
        }
    }
    metadata = {
        "applicant.name_roman": {"human_edited": True, "source_refs": []},
        "applicant.birth_date": {"human_edited": True, "source_refs": []},
    }

    merged = _merge_extracted_case_data(existing, extracted, metadata)

    assert merged["applicant"]["name_roman"] == "HUMAN CONFIRMED"
    assert merged["applicant"]["birth_date"] == "1990-01-02"
    assert merged["applicant"]["sex"] == "female"


def test_reextraction_preserves_human_edited_passport_field_metadata_only():
    existing = {
        "applicant.name_roman": {
            "human_edited": True,
            "source_refs": [{"document_id": "doc_reviewed"}],
        },
        "applicant.sex": {"human_edited": True, "source_refs": []},
    }
    extracted = {
        "applicant.name_roman": {
            "human_edited": False,
            "source_refs": [{"document_id": "doc_model"}],
        },
        "applicant.sex": {"human_edited": False, "source_refs": []},
    }

    merged = _merge_extracted_field_metadata(existing, extracted)

    assert merged["applicant.name_roman"] == existing["applicant.name_roman"]
    assert merged["applicant.sex"] == extracted["applicant.sex"]
