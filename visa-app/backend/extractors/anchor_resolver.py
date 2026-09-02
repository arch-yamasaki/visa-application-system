"""Resolve Gemini source locations into viewer anchors."""

from __future__ import annotations

import logging
import math

import pymupdf

from .gemini import _map_field_metadata

logger = logging.getLogger(__name__)

_STRUCTURAL_ANCHOR_KEYS = (
    "sheet_name",
    "cell",
    "row",
    "col",
    "paragraph_index",
    "table_index",
    "block_kind",
)


def _page_number(value) -> int:
    try:
        return int(value or 1)
    except (TypeError, ValueError):
        return 1


def _pdf_page_count(pdf_bytes: bytes) -> int:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def _iter_all_refs(meta: dict):
    refs = meta.get("source_refs", [])
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict):
                yield ref
    alternatives = meta.get("alternatives", [])
    if isinstance(alternatives, list):
        for alternative in alternatives:
            if not isinstance(alternative, dict):
                continue
            alt_refs = alternative.get("source_refs", [])
            if isinstance(alt_refs, list):
                for ref in alt_refs:
                    if isinstance(ref, dict):
                        yield ref


def _item_by_anchor_id(items: list[dict], anchor_id: str) -> dict | None:
    return next((item for item in items if item.get("anchor_id") == anchor_id), None)


def _structural_candidate(item: dict) -> dict:
    candidate = {"anchor_id": item.get("anchor_id")}
    for key in _STRUCTURAL_ANCHOR_KEYS:
        if key in item:
            candidate[key] = item[key]
    return candidate


def _set_resolved_structural_anchor(ref: dict, item: dict) -> None:
    anchor = {
        "type": item["type"],
        "status": "resolved",
        "resolver_type": "source_ref_location",
        "match_count": 1,
        "anchor_id": item.get("anchor_id"),
    }
    for key in _STRUCTURAL_ANCHOR_KEYS:
        if key in item:
            anchor[key] = item[key]
    ref["anchor"] = anchor


def _set_ambiguous_structural_anchor(ref: dict, anchor_type: str, items: list[dict]) -> None:
    ref["anchor"] = {
        "type": anchor_type,
        "status": "ambiguous",
        "resolver_type": "source_ref_location",
        "match_count": len(items),
        "candidates": [
            _structural_candidate(item)
            for item in items
        ],
    }


def _set_resolved_pdf_anchor(ref: dict, page: int, bbox: dict[str, float], resolver_type: str) -> None:
    ref["bbox"] = bbox
    ref["anchor"] = {
        "type": "pdf_bbox",
        "status": "resolved",
        "resolver_type": resolver_type,
        "bbox": bbox,
        "match_count": 1,
        "page": page,
    }


def _set_ambiguous_pdf_anchor(ref: dict, locations: list[dict]) -> None:
    ref["anchor"] = {
        "type": "pdf_bbox",
        "status": "ambiguous",
        "resolver_type": "source_ref_location",
        "match_count": len(locations),
        "candidates": locations,
    }


def _set_unresolved_anchor(ref: dict) -> None:
    ref["anchor"] = {
        "type": "source_location",
        "status": "not_found",
        "resolver_type": "source_ref_location",
        "match_count": 0,
    }


def _bbox_from_location(location: dict) -> dict[str, float] | None:
    bbox = location.get("bbox")
    if not isinstance(bbox, dict):
        return None
    try:
        normalized_bbox = {
            "y_min": float(bbox["y_min"]),
            "x_min": float(bbox["x_min"]),
            "y_max": float(bbox["y_max"]),
            "x_max": float(bbox["x_max"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if (
        normalized_bbox["y_min"] >= normalized_bbox["y_max"]
        or normalized_bbox["x_min"] >= normalized_bbox["x_max"]
    ):
        return None
    if any(
        not math.isfinite(value) or value < 0 or value > 1000
        for value in normalized_bbox.values()
    ):
        return None
    return normalized_bbox


def _resolve_ref_locations(
    ref: dict,
    pdf_bytes_map: dict[str, bytes],
    xlsx_cell_indexes: dict[str, list[dict]],
    docx_block_indexes: dict[str, list[dict]],
    pdf_page_counts: dict[str, int],
) -> str:
    document_id = str(ref.get("document_id") or "")
    valid_locations: list[dict] = []
    # 明示位置が正本。以前のresolverが付けたbboxへは戻さない。
    ref.pop("bbox", None)

    for location in ref.get("locations") or []:
        if not isinstance(location, dict):
            continue
        location_type = str(location.get("type") or "")

        if location_type == "xlsx_cell":
            item = _item_by_anchor_id(
                xlsx_cell_indexes.get(document_id, []),
                str(location.get("anchor_id") or ""),
            )
            if item:
                valid_locations.append(item)
            continue

        if location_type == "docx_block":
            item = _item_by_anchor_id(
                docx_block_indexes.get(document_id, []),
                str(location.get("anchor_id") or ""),
            )
            if item:
                valid_locations.append(item)
            continue

        if location_type == "pdf_bbox":
            bbox = _bbox_from_location(location)
            if not bbox or document_id not in pdf_bytes_map:
                continue
            page = location.get("page")
            if not isinstance(page, int) or isinstance(page, bool):
                continue
            if document_id not in pdf_page_counts:
                pdf_page_counts[document_id] = _pdf_page_count(pdf_bytes_map[document_id])
            if 1 <= page <= pdf_page_counts[document_id]:
                valid_locations.append({"type": "pdf_bbox", "page": page, "bbox": bbox})

    if len(valid_locations) == 1:
        location = valid_locations[0]
        if location.get("type") == "pdf_bbox":
            _set_resolved_pdf_anchor(ref, location["page"], location["bbox"], "source_ref_location")
        else:
            _set_resolved_structural_anchor(ref, location)
        return "resolved"

    if len(valid_locations) > 1:
        first_type = valid_locations[0].get("type")
        if all(location.get("type") == "pdf_bbox" for location in valid_locations):
            _set_ambiguous_pdf_anchor(ref, valid_locations)
        elif all(location.get("type") == first_type for location in valid_locations):
            _set_ambiguous_structural_anchor(ref, str(first_type), valid_locations)
        else:
            ref["anchor"] = {
                "type": "source_location",
                "status": "ambiguous",
                "resolver_type": "source_ref_location",
                "match_count": len(valid_locations),
                "candidates": valid_locations,
            }
        return "ambiguous"

    _set_unresolved_anchor(ref)
    return "not_found"


def sync_bbox_anchors(field_metadata: dict | list) -> dict:
    """Mirror legacy top-level bbox into nested anchor objects for display."""
    field_metadata = _map_field_metadata(field_metadata)
    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        for ref in _iter_all_refs(meta):
            if ref.get("bbox") and ref.get("anchor", {}).get("status") not in ("resolved", "ambiguous"):
                _set_resolved_pdf_anchor(
                    ref,
                    _page_number(ref.get("page")),
                    ref["bbox"],
                    "existing_bbox",
                )
    return field_metadata


def resolve_source_locations(
    field_metadata: dict | list,
    pdf_bytes_map: dict[str, bytes],
    xlsx_cell_indexes: dict[str, list[dict]] | None = None,
    docx_block_indexes: dict[str, list[dict]] | None = None,
) -> dict:
    """Validate explicit source_ref.locations and convert them to anchors."""
    field_metadata = _map_field_metadata(field_metadata)
    xlsx_cell_indexes = xlsx_cell_indexes or {}
    docx_block_indexes = docx_block_indexes or {}
    pdf_page_counts: dict[str, int] = {}
    resolved = ambiguous = not_found = skipped = 0

    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        for ref in _iter_all_refs(meta):
            if "locations" in ref:
                status = _resolve_ref_locations(
                    ref,
                    pdf_bytes_map,
                    xlsx_cell_indexes,
                    docx_block_indexes,
                    pdf_page_counts,
                )
                resolved += int(status == "resolved")
                ambiguous += int(status == "ambiguous")
                not_found += int(status == "not_found")
                continue

            if ref.get("bbox"):
                sync_bbox_anchors({"field": {"source_refs": [ref]}})
                resolved += int(ref.get("anchor", {}).get("status") == "resolved")
                ambiguous += int(ref.get("anchor", {}).get("status") == "ambiguous")
                continue

            # locations がない保存済みデータは、既存anchorをそのまま表示する。
            # 新しい位置をquoteから推測したり、既存anchorを上書きしたりしない。
            anchor_status = ref.get("anchor", {}).get("status")
            resolved += int(anchor_status == "resolved")
            ambiguous += int(anchor_status == "ambiguous")
            skipped += int(anchor_status not in ("resolved", "ambiguous"))

    logger.info(
        "source_location_resolver_metric event=completed resolved=%d ambiguous=%d not_found=%d skipped=%d",
        resolved,
        ambiguous,
        not_found,
        skipped,
    )
    return field_metadata


def anchor_coverage(field_metadata: dict | list) -> dict:
    """Return field-level anchor coverage for refs that have document evidence."""
    field_metadata = _map_field_metadata(field_metadata)
    total = resolved = displayable = 0
    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        origin = meta.get("origin")
        if origin and origin != "document":
            continue
        if meta.get("has_value") is False:
            continue
        real_refs = [
            ref
            for ref in _iter_all_refs(meta)
            if ref.get("document_id") or ref.get("text_quote")
        ]
        if meta.get("has_value") is not True and not real_refs:
            continue
        total += 1
        best = None
        for ref in real_refs:
            anchor = ref.get("anchor") or {}
            if anchor.get("status") == "resolved" or ref.get("bbox"):
                best = "resolved"
                break
            if (
                anchor.get("status") == "ambiguous"
                and anchor.get("candidates")
                and any(
                    candidate.get("bbox") or candidate.get("anchor_id")
                    for candidate in anchor.get("candidates")
                    if isinstance(candidate, dict)
                )
            ):
                best = "candidates"
        if best == "resolved":
            resolved += 1
            displayable += 1
        elif best == "candidates":
            displayable += 1
    return {
        "total_fields": total,
        "resolved_fields": resolved,
        "displayable_fields": displayable,
    }
