"""Convert loaded files into Gemini-ready document groups."""

import time
from collections.abc import Callable

from .document_models import LoadedDocument, PreparedDocuments


DocumentEventLogger = Callable[[str, LoadedDocument, dict], None]


def _extension(file_name: str) -> str:
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def prepare_documents(
    documents: list[LoadedDocument],
    event_logger: DocumentEventLogger | None = None,
) -> PreparedDocuments:
    prepared = PreparedDocuments()

    for document in documents:
        started_at = time.monotonic()
        ext = _extension(document.file_name)

        if ext == "pdf":
            prepared.pdf_contents.append((document.document_id, document.content))
            prepared.image_entries.append(
                (document.document_id, document.file_name, document.content)
            )
            if event_logger:
                event_logger(
                    "document_classified",
                    document,
                    {
                        "ext": ext,
                        "route": "pdf_direct",
                        "bytes": len(document.content),
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                    },
                )
        elif ext == "xlsx":
            from .xlsx import build_xlsx_cell_index, extract_xlsx

            ocr = extract_xlsx(document.content, document.document_id)
            text = "\n".join(page.text for page in ocr.pages)
            prepared.text_contents.append((document.document_id, text))
            prepared.xlsx_cell_indexes[document.document_id] = build_xlsx_cell_index(
                document.content,
                document.document_id,
            )
            if event_logger:
                event_logger(
                    "document_text_extracted",
                    document,
                    {
                        "ext": ext,
                        "pages": len(ocr.pages),
                        "text_chars": len(text),
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                    },
                )
        elif ext == "docx":
            from .docx_text import build_docx_block_index, extract_docx

            ocr = extract_docx(document.content, document.document_id)
            text = "\n".join(page.text for page in ocr.pages)
            prepared.text_contents.append((document.document_id, text))
            prepared.docx_block_indexes[document.document_id] = build_docx_block_index(
                document.content,
                document.document_id,
            )
            if event_logger:
                event_logger(
                    "document_text_extracted",
                    document,
                    {
                        "ext": ext,
                        "pages": len(ocr.pages),
                        "text_chars": len(text),
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                    },
                )
        elif ext in ("png", "jpg", "jpeg"):
            prepared.image_entries.append(
                (document.document_id, document.file_name, document.content)
            )
            if event_logger:
                event_logger(
                    "document_classified",
                    document,
                    {
                        "ext": ext,
                        "route": "image_direct",
                        "bytes": len(document.content),
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                    },
                )

    prepared.pdf_bytes_map = {
        document_id: content for document_id, content in prepared.pdf_contents
    }
    return prepared
