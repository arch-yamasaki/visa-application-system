"""Resolve source_refs into viewer anchors.

Gemini returns evidence text. The backend resolves that evidence into a
format-specific location that the viewer can trust. Keep the resolved anchor
nested under ``source_ref["anchor"]`` while preserving legacy top-level
``bbox`` for the existing PDF viewer.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

import pymupdf

from .gemini import _map_field_metadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PdfTextMatch:
    bbox: dict[str, float]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = re.sub(r"[\s\u3000]+", "", normalized)
    normalized = re.sub(r"[、。,.，．]", "", normalized)
    return normalized.lower()


def _page_number(value) -> int:
    try:
        return int(value or 1)
    except (TypeError, ValueError):
        return 1


def _normalized_bbox(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    page_width: float,
    page_height: float,
) -> dict[str, float]:
    return {
        "y_min": round((y_min / page_height) * 1000, 2),
        "x_min": round((x_min / page_width) * 1000, 2),
        "y_max": round((y_max / page_height) * 1000, 2),
        "x_max": round((x_max / page_width) * 1000, 2),
    }


def _find_pdf_text_matches(
    pdf_bytes: bytes,
    page_num: int,
    locator_text: str,
) -> list[_PdfTextMatch]:
    target = _normalize_text(locator_text)
    if not target:
        return []

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page_index = page_num - 1
        if page_index < 0 or page_index >= len(doc):
            return []
        page = doc[page_index]
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        words = page.get_text("words")
        matches: list[_PdfTextMatch] = []

        for start in range(len(words)):
            x_min = y_min = x_max = y_max = None
            joined = ""
            for end in range(start, len(words)):
                x0, y0, x1, y1, text = words[end][:5]
                joined += _normalize_text(str(text))
                x_min = x0 if x_min is None else min(x_min, x0)
                y_min = y0 if y_min is None else min(y_min, y0)
                x_max = x1 if x_max is None else max(x_max, x1)
                y_max = y1 if y_max is None else max(y_max, y1)
                if joined == target:
                    matches.append(_PdfTextMatch(
                        bbox=_normalized_bbox(
                            float(x_min),
                            float(y_min),
                            float(x_max),
                            float(y_max),
                            page_width,
                            page_height,
                        )
                    ))
                    break
                if len(joined) >= len(target):
                    break
        return matches
    finally:
        doc.close()


def _set_resolved_pdf_anchor(ref: dict, bbox: dict[str, float], resolver_type: str) -> None:
    ref["bbox"] = bbox
    ref["anchor"] = {
        "type": "pdf_bbox",
        "status": "resolved",
        "resolver_type": resolver_type,
        "bbox": bbox,
        "match_count": 1,
    }


def _set_unresolved_pdf_anchor(ref: dict, status: str, resolver_type: str, match_count: int) -> None:
    if ref.get("anchor", {}).get("status") == "resolved":
        return
    ref["anchor"] = {
        "type": "pdf_bbox",
        "status": status,
        "resolver_type": resolver_type,
        "match_count": match_count,
    }


def _set_resolved_structural_anchor(ref: dict, item: dict, resolver_type: str) -> None:
    anchor = {
        "type": item["type"],
        "status": "resolved",
        "resolver_type": resolver_type,
        "match_count": 1,
        "anchor_id": item.get("anchor_id"),
    }
    for key in (
        "sheet_name",
        "cell",
        "row",
        "col",
        "paragraph_index",
        "table_index",
        "block_kind",
    ):
        if key in item:
            anchor[key] = item[key]
    ref["anchor"] = anchor


def _set_unresolved_structural_anchor(
    ref: dict,
    anchor_type: str,
    status: str,
    resolver_type: str,
    match_count: int,
) -> None:
    if ref.get("anchor", {}).get("status") == "resolved":
        return
    ref["anchor"] = {
        "type": anchor_type,
        "status": status,
        "resolver_type": resolver_type,
        "match_count": match_count,
    }


def _resolve_from_text_index(
    ref: dict,
    items: list[dict],
    *,
    anchor_type: str,
    resolver_type: str,
) -> str:
    target = _normalize_text(str(ref.get("text_quote") or ""))
    if not target:
        return "skipped"
    exact_matches = [
        item
        for item in items
        if target == _normalize_text(str(item.get("text") or ""))
    ]
    matches = exact_matches or [
        item
        for item in items
        if target in _normalize_text(str(item.get("text") or ""))
    ]
    if len(matches) == 1:
        _set_resolved_structural_anchor(ref, matches[0], resolver_type)
        return "resolved"
    if len(matches) > 1:
        _set_unresolved_structural_anchor(ref, anchor_type, "ambiguous", resolver_type, len(matches))
        return "ambiguous"
    _set_unresolved_structural_anchor(ref, anchor_type, "not_found", resolver_type, 0)
    return "not_found"


def sync_bbox_anchors(field_metadata: dict | list) -> dict:
    """Mirror legacy top-level bbox into nested anchor objects."""
    field_metadata = _map_field_metadata(field_metadata)
    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        for ref in meta.get("source_refs", []):
            if not isinstance(ref, dict):
                continue
            bbox = ref.get("bbox")
            if bbox and ref.get("anchor", {}).get("status") != "resolved":
                _set_resolved_pdf_anchor(ref, bbox, "gemini_bbox")
    return field_metadata


def resolve_anchors(
    field_metadata: dict | list,
    pdf_bytes_map: dict[str, bytes],
    xlsx_cell_indexes: dict[str, list[dict]] | None = None,
    docx_block_indexes: dict[str, list[dict]] | None = None,
) -> dict:
    """Resolve anchors for source refs where deterministic indexes are available."""
    field_metadata = _map_field_metadata(field_metadata)
    xlsx_cell_indexes = xlsx_cell_indexes or {}
    docx_block_indexes = docx_block_indexes or {}
    resolved = ambiguous = not_found = skipped = 0

    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        for ref in meta.get("source_refs", []):
            if not isinstance(ref, dict):
                continue
            bbox = ref.get("bbox")
            if bbox:
                _set_resolved_pdf_anchor(ref, bbox, "existing_bbox")
                resolved += 1
                continue

            document_id = str(ref.get("document_id") or "")
            text_quote = str(ref.get("text_quote") or "")
            if not document_id or not text_quote:
                skipped += 1
                continue
            if document_id in xlsx_cell_indexes:
                status = _resolve_from_text_index(
                    ref,
                    xlsx_cell_indexes[document_id],
                    anchor_type="xlsx_cell",
                    resolver_type="xlsx_cell_index",
                )
                resolved += int(status == "resolved")
                ambiguous += int(status == "ambiguous")
                not_found += int(status == "not_found")
                skipped += int(status == "skipped")
                continue
            if document_id in docx_block_indexes:
                status = _resolve_from_text_index(
                    ref,
                    docx_block_indexes[document_id],
                    anchor_type="docx_block",
                    resolver_type="docx_block_index",
                )
                resolved += int(status == "resolved")
                ambiguous += int(status == "ambiguous")
                not_found += int(status == "not_found")
                skipped += int(status == "skipped")
                continue
            if document_id not in pdf_bytes_map:
                skipped += 1
                continue
            page = _page_number(ref.get("page"))
            matches = _find_pdf_text_matches(pdf_bytes_map[document_id], page, text_quote)
            if len(matches) == 1:
                _set_resolved_pdf_anchor(ref, matches[0].bbox, "pdf_text_layer")
                resolved += 1
            elif len(matches) > 1:
                _set_unresolved_pdf_anchor(ref, "ambiguous", "pdf_text_layer", len(matches))
                ambiguous += 1
            else:
                _set_unresolved_pdf_anchor(ref, "not_found", "pdf_text_layer", 0)
                not_found += 1

    logger.info(
        "anchor_resolver_metric event=completed resolved=%d ambiguous=%d not_found=%d skipped=%d",
        resolved,
        ambiguous,
        not_found,
        skipped,
    )
    return field_metadata
