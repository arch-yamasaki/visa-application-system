"""Document helper tests for main API module."""

import io

import openpyxl
import pytest
from fastapi import HTTPException

from main import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    _file_extension,
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
