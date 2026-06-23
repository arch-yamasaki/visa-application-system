"""Document preprocessor format support tests."""

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
