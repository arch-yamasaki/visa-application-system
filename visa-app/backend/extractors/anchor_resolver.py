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
from collections import Counter
from dataclasses import dataclass

import pymupdf

from .gemini import _map_field_metadata

logger = logging.getLogger(__name__)

MIN_SUBSTRING_MATCH_CHARS = 4

# ambiguous時に保持する候補位置の上限。頻出文字列(年号など)の全件表示は無意味なので絞る。
MAX_AMBIGUOUS_CANDIDATES = 3


@dataclass(frozen=True)
class _PdfTextMatch:
    page: int
    bbox: dict[str, float]


@dataclass(frozen=True)
class _PdfPageWords:
    width: float
    height: float
    # (normalized_text, x0, y0, x1, y1)
    words: list[tuple[str, float, float, float, float]]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = re.sub(r"[\s\u3000]+", "", normalized)
    normalized = re.sub(r"[、。,.，．()（）]", "", normalized)
    return normalized.lower()


def _page_number(value) -> int:
    try:
        return int(value or 1)
    except (TypeError, ValueError):
        return 1


def _has_page(value) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _locator_texts(text_quote: str) -> list[str]:
    """Return search targets ordered from most to least specific.

    The word-join matcher requires exact equality, so a truncated target must
    end on a word boundary — a mid-word cut can never match.
    """
    quote = " ".join((text_quote or "").split())
    candidates = []
    if quote:
        candidates.append(quote)
        if len(quote) > 80:
            head = quote[:81]
            if " " in head:
                candidates.append(head[: head.rfind(" ")])
    candidates.extend(re.findall(r"\d[\d\-]{2,}\d", quote))

    seen = set()
    locator_texts = []
    for candidate in candidates:
        normalized = _normalize_text(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            locator_texts.append(candidate)
    return locator_texts


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


class _PdfTextIndex:
    """Per-document cache of page words so every ref reuses one parse."""

    def __init__(self, pdf_bytes: bytes) -> None:
        self._doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        self._pages: dict[int, _PdfPageWords | None] = {}

    @property
    def page_count(self) -> int:
        return len(self._doc)

    def page_words(self, page_num: int) -> _PdfPageWords | None:
        if page_num not in self._pages:
            page_index = page_num - 1
            if page_index < 0 or page_index >= len(self._doc):
                self._pages[page_num] = None
            else:
                page = self._doc[page_index]
                self._pages[page_num] = _PdfPageWords(
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    words=[
                        (
                            _normalize_text(str(word[4])),
                            float(word[0]),
                            float(word[1]),
                            float(word[2]),
                            float(word[3]),
                        )
                        for word in page.get_text("words")
                    ],
                )
        return self._pages[page_num]

    def close(self) -> None:
        self._doc.close()


def _find_matches_on_pages(
    index: _PdfTextIndex,
    page_nums: list[int],
    target: str,
) -> list[_PdfTextMatch]:
    matches: list[_PdfTextMatch] = []
    for page_num in page_nums:
        page = index.page_words(page_num)
        if page is None:
            continue
        words = page.words
        for start in range(len(words)):
            x_min = y_min = x_max = y_max = None
            joined = ""
            for end in range(start, len(words)):
                text, x0, y0, x1, y1 = words[end]
                joined += text
                x_min = x0 if x_min is None else min(x_min, x0)
                y_min = y0 if y_min is None else min(y_min, y0)
                x_max = x1 if x_max is None else max(x_max, x1)
                y_max = y1 if y_max is None else max(y_max, y1)
                if joined == target:
                    matches.append(_PdfTextMatch(
                        page=page_num,
                        bbox=_normalized_bbox(
                            x_min,
                            y_min,
                            x_max,
                            y_max,
                            page.width,
                            page.height,
                        )
                    ))
                    break
                if len(joined) >= len(target):
                    break
    return matches


def _find_pdf_text_matches(
    index: _PdfTextIndex,
    page_sequences: list[list[int]],
    locator_texts: list[str],
) -> list[_PdfTextMatch]:
    """Search targets strongest-first; each target exhausts all page groups.

    A weaker fallback target (e.g. a number pattern) must not win on the
    stated page before a stronger target gets its cross-page chance.
    """
    targets = [
        _normalize_text(locator_text)
        for locator_text in locator_texts
        if _normalize_text(locator_text)
    ]
    if not targets:
        return []

    for target in targets:
        for page_nums in page_sequences:
            matches = _find_matches_on_pages(index, page_nums, target)
            if matches:
                return matches
    return []


def _set_resolved_pdf_anchor(
    ref: dict,
    bbox: dict[str, float],
    resolver_type: str,
    page: int | None = None,
) -> None:
    ref["bbox"] = bbox
    anchor = {
        "type": "pdf_bbox",
        "status": "resolved",
        "resolver_type": resolver_type,
        "bbox": bbox,
        "match_count": 1,
    }
    if page is not None:
        anchor["page"] = page
    ref["anchor"] = anchor


def _set_unresolved_pdf_anchor(ref: dict, status: str, resolver_type: str, match_count: int) -> None:
    if ref.get("anchor", {}).get("status") == "resolved":
        return
    ref["anchor"] = {
        "type": "pdf_bbox",
        "status": status,
        "resolver_type": resolver_type,
        "match_count": match_count,
    }


def _set_ambiguous_pdf_anchor(
    ref: dict,
    resolver_type: str,
    matches: list[_PdfTextMatch],
) -> None:
    """複数一致は候補位置ごと保存し、ビューアで全候補を提示できるようにする。"""
    if ref.get("anchor", {}).get("status") == "resolved":
        return
    ref["anchor"] = {
        "type": "pdf_bbox",
        "status": "ambiguous",
        "resolver_type": resolver_type,
        "match_count": len(matches),
        "candidates": [
            {"page": match.page, "bbox": match.bbox}
            for match in matches[:MAX_AMBIGUOUS_CANDIDATES]
        ],
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


def _match_text_index_items(items: list[dict], target: str) -> list[dict]:
    exact_matches = [
        item
        for item in items
        if target == _normalize_text(str(item.get("text") or ""))
    ]
    if exact_matches:
        return exact_matches
    if len(target) >= MIN_SUBSTRING_MATCH_CHARS:
        return [
            item
            for item in items
            if target in _normalize_text(str(item.get("text") or ""))
        ]
    return []


def _match_multi_cell_quote(items: list[dict], text_quote: str) -> list[dict]:
    """タブ/改行でセルをまたいだquote(質問セル+回答セル連結)を解決する。

    末尾セグメント(回答セル)で照合し、複数一致なら同一シート同一行に
    質問セグメントが載っている行へ絞り込む。
    """
    segments = [seg for seg in re.split(r"[\t\n]+", text_quote or "") if seg.strip()]
    if len(segments) <= 1:
        return []
    answer_target = _normalize_text(segments[-1])
    if not answer_target:
        return []
    matches = _match_text_index_items(items, answer_target)
    if len(matches) <= 1:
        return matches

    question_targets = [
        _normalize_text(segment)
        for segment in segments[:-1]
        if _normalize_text(segment)
    ]
    if not question_targets:
        return matches

    def _row_has_question(match: dict) -> bool:
        if match.get("row") is None:
            # 行の概念がないindex(docx等)では絞り込まない
            return True
        return any(
            question_target in _normalize_text(str(item.get("text") or ""))
            for item in items
            if item.get("sheet_name") == match.get("sheet_name")
            and item.get("row") == match.get("row")
            and item is not match
            for question_target in question_targets
        )

    narrowed = [match for match in matches if _row_has_question(match)]
    return narrowed or matches


def _matches_for_quote(items: list[dict], text_quote: str) -> list[dict]:
    target = _normalize_text(text_quote)
    if not target:
        return []
    matches = _match_text_index_items(items, target)
    if not matches:
        matches = _match_multi_cell_quote(items, text_quote)
    return matches


def _resolve_from_text_index(
    ref: dict,
    items: list[dict],
    *,
    anchor_type: str,
    resolver_type: str,
) -> str:
    text_quote = str(ref.get("text_quote") or "")
    if not _normalize_text(text_quote):
        return "skipped"
    matches = _matches_for_quote(items, text_quote)
    if len(matches) == 1:
        _set_resolved_structural_anchor(ref, matches[0], resolver_type)
        return "resolved"
    if len(matches) > 1:
        _set_unresolved_structural_anchor(ref, anchor_type, "ambiguous", resolver_type, len(matches))
        return "ambiguous"
    _set_unresolved_structural_anchor(ref, anchor_type, "not_found", resolver_type, 0)
    return "not_found"


def _preferred_sheets(field_metadata: dict) -> dict[str, str]:
    """document_idごとに、resolved xlsx anchor が最も集まるシートを返す(単独首位のみ)。

    シート=申請人のワークブック(8名分など)で、共通の回答値が全シートに
    存在して ambiguous になるケースを、本人のシートへ寄せるためのヒント。
    """
    counts: dict[str, Counter] = {}
    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        for ref in _iter_all_refs(meta):
            anchor = ref.get("anchor") or {}
            if (
                anchor.get("type") == "xlsx_cell"
                and anchor.get("status") == "resolved"
                and anchor.get("sheet_name")
            ):
                doc_id = str(ref.get("document_id") or "")
                counts.setdefault(doc_id, Counter())[anchor["sheet_name"]] += 1
    preferred: dict[str, str] = {}
    for doc_id, counter in counts.items():
        top = counter.most_common(2)
        if len(top) == 1 or top[0][1] > top[1][1]:
            preferred[doc_id] = top[0][0]
    return preferred


def _apply_sheet_preference(
    field_metadata: dict,
    xlsx_cell_indexes: dict[str, list[dict]],
) -> int:
    """ambiguousなxlsx anchorを、優先シート内で一意ならresolvedへ昇格する。"""
    preferred = _preferred_sheets(field_metadata)
    if not preferred:
        return 0
    promoted = 0
    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        for ref in _iter_all_refs(meta):
            anchor = ref.get("anchor") or {}
            if anchor.get("type") != "xlsx_cell" or anchor.get("status") != "ambiguous":
                continue
            doc_id = str(ref.get("document_id") or "")
            sheet = preferred.get(doc_id)
            items = xlsx_cell_indexes.get(doc_id)
            if not sheet or not items:
                continue
            matches = _matches_for_quote(items, str(ref.get("text_quote") or ""))
            sheet_matches = [m for m in matches if m.get("sheet_name") == sheet]
            if len(sheet_matches) == 1:
                _set_resolved_structural_anchor(
                    ref, sheet_matches[0], "xlsx_cell_index_sheet_preference"
                )
                promoted += 1
    if promoted:
        logger.info("anchor_resolver_metric event=sheet_preference promoted=%d", promoted)
    return promoted


def anchor_coverage(field_metadata: dict | list) -> dict:
    """field単位のanchorカバレッジ。

    証跡(document_idまたはquoteを持つref)があるfieldのうち、
    resolved(確定表示可) / displayable(候補表示含め何か光る) の数を返す。
    """
    field_metadata = _map_field_metadata(field_metadata)
    total = resolved = displayable = 0
    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        real_refs = [
            ref
            for ref in _iter_all_refs(meta)
            if ref.get("document_id") or ref.get("text_quote")
        ]
        if not real_refs:
            continue
        total += 1
        best = None
        for ref in real_refs:
            anchor = ref.get("anchor") or {}
            if anchor.get("status") == "resolved" or ref.get("bbox"):
                best = "resolved"
                break
            if anchor.get("status") == "ambiguous" and anchor.get("candidates"):
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


def sync_bbox_anchors(field_metadata: dict | list) -> dict:
    """Mirror legacy top-level bbox into nested anchor objects."""
    field_metadata = _map_field_metadata(field_metadata)
    for meta in field_metadata.values():
        if not isinstance(meta, dict):
            continue
        for ref in _iter_all_refs(meta):
            bbox = ref.get("bbox")
            anchor_status = ref.get("anchor", {}).get("status")
            if bbox and anchor_status not in ("resolved", "ambiguous"):
                _set_resolved_pdf_anchor(ref, bbox, "gemini_bbox", _page_number(ref.get("page")))
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
    pdf_indexes: dict[str, _PdfTextIndex] = {}

    try:
        for meta in field_metadata.values():
            if not isinstance(meta, dict):
                continue
            for ref in _iter_all_refs(meta):
                bbox = ref.get("bbox")
                if bbox:
                    anchor_status = ref.get("anchor", {}).get("status")
                    if anchor_status == "ambiguous":
                        ambiguous += 1
                    elif anchor_status == "resolved":
                        # A prior run may have resolved on a page other than
                        # ref["page"]; rewriting from ref["page"] would corrupt
                        # anchor.page, so keep the anchor as-is.
                        resolved += 1
                    else:
                        _set_resolved_pdf_anchor(ref, bbox, "existing_bbox", _page_number(ref.get("page")))
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
                index = pdf_indexes.get(document_id)
                if index is None:
                    index = _PdfTextIndex(pdf_bytes_map[document_id])
                    pdf_indexes[document_id] = index
                page_value = ref.get("page")
                locator_texts = _locator_texts(text_quote)
                if _has_page(page_value):
                    page = _page_number(page_value)
                    other_pages = [num for num in range(1, index.page_count + 1) if num != page]
                    page_sequences = [[page], other_pages]
                else:
                    page_sequences = [list(range(1, index.page_count + 1))]
                matches = _find_pdf_text_matches(index, page_sequences, locator_texts)
                if len(matches) == 1:
                    _set_resolved_pdf_anchor(ref, matches[0].bbox, "pdf_text_layer", matches[0].page)
                    resolved += 1
                elif len(matches) > 1:
                    _set_ambiguous_pdf_anchor(ref, "pdf_text_layer", matches)
                    ambiguous += 1
                else:
                    _set_unresolved_pdf_anchor(ref, "not_found", "pdf_text_layer", 0)
                    not_found += 1
        # 2nd pass: 複数シートで一致したxlsx ambiguousを、このケースの
        # resolved anchorが集中するシート(=申請人のシート)へ絞り込む
        promoted = _apply_sheet_preference(field_metadata, xlsx_cell_indexes)
        resolved += promoted
        ambiguous -= promoted
    finally:
        for index in pdf_indexes.values():
            index.close()

    logger.info(
        "anchor_resolver_metric event=completed resolved=%d ambiguous=%d not_found=%d skipped=%d",
        resolved,
        ambiguous,
        not_found,
        skipped,
    )
    return field_metadata
