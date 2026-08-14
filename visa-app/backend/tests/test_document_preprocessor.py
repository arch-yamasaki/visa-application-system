"""Document preprocessor format support tests."""

import pymupdf
import pytest

from extractors.document_models import LoadedDocument
from extractors.document_preprocessor import prepare_documents


def test_prepare_documents_ignores_legacy_office_formats():
    documents = [
        LoadedDocument("doc_xls", "legacy.xls", "applicant_document_bundle", b"not-xlsx"),
        LoadedDocument("doc_doc", "legacy.doc", "applicant_document_bundle", b"not-docx"),
    ]

    prepared = prepare_documents(documents)

    assert prepared.text_contents == []
    assert prepared.xlsx_cell_indexes == {}
    assert prepared.docx_block_indexes == {}


def test_prepare_documents_ignores_tiff_images():
    documents = [
        LoadedDocument("doc_tiff", "scan.tiff", "applicant_document_bundle", b"not-tiff"),
    ]

    prepared = prepare_documents(documents)

    assert prepared.image_entries == []


def test_prepare_documents_records_byte_derived_pdf_page_count():
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.new_page()
    content = pdf.tobytes()
    pdf.close()

    prepared = prepare_documents([
        LoadedDocument("doc_pdf", "bundle.pdf", "applicant_document_bundle", content),
    ])

    assert prepared.page_counts == {"doc_pdf": 2}
    assert prepared.document_kinds == {"doc_pdf": "pdf"}


def test_prepare_documents_records_image_as_one_page():
    prepared = prepare_documents([
        LoadedDocument("doc_image", "passport.jpg", "applicant_document_bundle", b"jpeg"),
    ])

    assert prepared.page_counts == {"doc_image": 1}
    assert prepared.document_kinds == {"doc_image": "image"}


def test_prepare_documents_reports_invalid_pdf_before_extraction():
    with pytest.raises(ValueError, match="document_id=doc_invalid"):
        prepare_documents([
            LoadedDocument("doc_invalid", "broken.pdf", "applicant_document_bundle", b"not-pdf"),
        ])
