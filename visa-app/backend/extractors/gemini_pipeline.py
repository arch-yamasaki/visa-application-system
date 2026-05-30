"""Shared Gemini extraction pipeline for GCS and local file inputs."""

import logging
import os
import time
from collections.abc import Callable

from google.genai import types as genai_types

from .bbox_locator import locate_bboxes
from .document_models import LoadedDocument, PreparedDocuments
from .gemini import (
    EXTRACTION_SCOPES,
    _get_client,
    extract_all_scopes,
    extract_pdf_direct,
    extract_text_only,
    extract_with_images,
)
from .types import ExtractionResult
from .vision import ocr_document

logger = logging.getLogger(__name__)

PipelineEventLogger = Callable[[str, dict], None]


def _mime_for_image(image_bytes: bytes) -> str:
    return "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"


def build_gemini_contents(prepared: PreparedDocuments) -> list:
    parts: list = []
    for document_id, text in prepared.text_contents:
        parts.append(f"--- document: {document_id} ---\n{text}")
    for document_id, pdf_bytes in prepared.pdf_contents:
        parts.append(
            genai_types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        )
        parts.append(f"(document_id: {document_id})")
    for document_id, file_name, image_bytes in prepared.image_entries:
        if file_name.lower().endswith(".pdf"):
            continue
        parts.append(
            genai_types.Part.from_bytes(
                data=image_bytes,
                mime_type=_mime_for_image(image_bytes),
            )
        )
        parts.append(f"(document_id: {document_id})")
    return parts


def _log_event(
    event_logger: PipelineEventLogger | None,
    event: str,
    **fields,
) -> None:
    if event_logger:
        event_logger(event, fields)


def attach_bboxes(
    result: ExtractionResult,
    prepared: PreparedDocuments,
    *,
    case_id: str,
    run_id: str | None = None,
    enabled: bool = True,
    event_logger: PipelineEventLogger | None = None,
) -> ExtractionResult:
    if not prepared.pdf_contents:
        return result
    if not enabled or os.environ.get("ENABLE_BBOX_LOCATOR", "true").lower() != "true":
        logger.info("Bbox locator skipped case_id=%s reason=disabled", case_id)
        return result

    logger.info(
        "Bbox locator started case_id=%s pdfs=%d metadata_fields=%d",
        case_id,
        len(prepared.pdf_contents),
        len(result.field_metadata),
    )
    started_at = time.monotonic()
    try:
        result.field_metadata = locate_bboxes(
            result.field_metadata,
            prepared.pdf_bytes_map,
        )
    except Exception as exc:
        logger.warning(
            "Bbox locator failed case_id=%s error_type=%s",
            case_id,
            type(exc).__name__,
            exc_info=True,
        )
        _log_event(
            event_logger,
            "bbox_failed",
            run_id=run_id,
            case_id=case_id,
            pdfs=len(prepared.pdf_contents),
            metadata_fields=len(result.field_metadata),
            error_type=type(exc).__name__,
            elapsed_ms=round((time.monotonic() - started_at) * 1000),
        )
        return result

    bbox_refs = sum(
        1
        for meta in result.field_metadata.values()
        for ref in meta.get("source_refs", [])
        if ref.get("bbox")
    )
    _log_event(
        event_logger,
        "bbox_complete",
        run_id=run_id,
        case_id=case_id,
        pdfs=len(prepared.pdf_contents),
        metadata_fields=len(result.field_metadata),
        bbox_refs=bbox_refs,
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
    )
    logger.info("Bbox locator completed case_id=%s", case_id)
    return result


def extract_documents(
    case_meta: dict,
    manifest_documents: list[dict],
    loaded_documents: list[LoadedDocument],
    prepared: PreparedDocuments,
    *,
    pattern: str = "auto",
    scoped: bool = True,
    run_id: str | None = None,
    case_id: str | None = None,
    attach_bbox_refs: bool = True,
    event_logger: PipelineEventLogger | None = None,
) -> ExtractionResult:
    case_id = case_id or case_meta.get("case_id", "")

    if scoped:
        client = _get_client()
        scoped_names = [*EXTRACTION_SCOPES, "review"]
        contents_by_scope = {
            scope: build_gemini_contents(prepared)
            for scope in scoped_names
        }
        documents_by_scope = {
            scope: list(manifest_documents)
            for scope in scoped_names
        }
        logger.info(
            "Gemini scoped contents case_id=%s parts=%s documents=%s",
            case_id,
            {scope: len(parts) for scope, parts in contents_by_scope.items()},
            {scope: len(docs) for scope, docs in documents_by_scope.items()},
        )
        for scope, parts in contents_by_scope.items():
            _log_event(
                event_logger,
                "scope_input_built",
                run_id=run_id,
                case_id=case_id,
                scope=scope,
                parts=len(parts),
                documents=len(documents_by_scope[scope]),
            )

        result = extract_all_scopes(
            client,
            contents_by_scope,
            case_meta,
            documents_by_scope,
            text_contents=prepared.text_contents or None,
            run_id=run_id,
            case_id=case_id,
        )
        return attach_bboxes(
            result,
            prepared,
            case_id=case_id,
            run_id=run_id,
            enabled=attach_bbox_refs,
            event_logger=event_logger,
        )

    if pattern == "auto":
        has_pdfs = any(
            document.file_name.lower().endswith(".pdf")
            for document in loaded_documents
        )
        has_images_only = prepared.image_entries and not has_pdfs
        pattern = "text_and_image" if has_images_only else "pdf_direct"

    if pattern == "text_only":
        ocr_results = [
            ocr_document(document.content, document.file_name, document.document_id)
            for document in loaded_documents
            if any(entry[0] == document.document_id for entry in prepared.image_entries)
        ]
        return extract_text_only(
            ocr_results,
            case_meta,
            manifest_documents,
            text_contents=prepared.text_contents or None,
        )
    if pattern == "pdf_direct":
        result = extract_pdf_direct(
            prepared.pdf_contents,
            case_meta,
            manifest_documents,
            text_contents=prepared.text_contents or None,
        )
        return attach_bboxes(
            result,
            prepared,
            case_id=case_id,
            run_id=run_id,
            enabled=attach_bbox_refs,
            event_logger=event_logger,
        )

    ocr_results = [
        ocr_document(document.content, document.file_name, document.document_id)
        for document in loaded_documents
        if any(entry[0] == document.document_id for entry in prepared.image_entries)
    ]
    result = extract_with_images(
        ocr_results,
        prepared.pdf_contents,
        case_meta,
        manifest_documents,
        text_contents=prepared.text_contents or None,
    )
    return attach_bboxes(
        result,
        prepared,
        case_id=case_id,
        run_id=run_id,
        enabled=attach_bbox_refs,
        event_logger=event_logger,
    )
