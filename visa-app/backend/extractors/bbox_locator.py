"""Gemini bbox取得: 未解決のPDF source_refにbboxを付与するfallback。

対象はfield allowlistではなく「PDF由来で位置未解決のref全部」。
コストは (document, page) 単位のGemini呼び出しなので、候補refが増えても
参照ページ数以上には増えない。品質フィルタと重複集約が候補数の防御になる。
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymupdf

from .anchor_resolver import _page_number
from .gemini import get_bboxes_for_page, _map_field_metadata

logger = logging.getLogger(__name__)

# 抽出値のエコー(実文書に存在しないquote)はbboxを引けないので候補にしない。
_VALUE_ECHO_QUOTES = {"true", "false", "null", "none"}
_MIN_LOCATOR_CHARS = 2
_BboxTarget = tuple[str, int | None, int]


def _is_low_quality_locator(locator_text: str) -> bool:
    normalized = locator_text.strip().lower()
    if len(normalized) < _MIN_LOCATOR_CHARS:
        return True
    return normalized in _VALUE_ECHO_QUOTES


def _locator_text(text_quote: str) -> str:
    """Return a short locator text for bbox detection."""
    quote = " ".join((text_quote or "").split())
    return quote[:80]


def _iter_refs_for_bbox(meta: dict):
    refs = meta.get("source_refs", [])
    if isinstance(refs, list):
        for ref_index, ref in enumerate(refs):
            if isinstance(ref, dict):
                yield None, ref_index, ref
    alternatives = meta.get("alternatives", [])
    if isinstance(alternatives, list):
        for alt_index, alternative in enumerate(alternatives):
            if not isinstance(alternative, dict):
                continue
            alt_refs = alternative.get("source_refs", [])
            if not isinstance(alt_refs, list):
                continue
            for ref_index, ref in enumerate(alt_refs):
                if isinstance(ref, dict):
                    yield alt_index, ref_index, ref


def _get_target_ref(field_metadata: dict, target: _BboxTarget) -> dict | None:
    field_path, alt_index, ref_index = target
    meta = field_metadata.get(field_path, {})
    if not isinstance(meta, dict):
        return None
    if alt_index is None:
        refs = meta.get("source_refs", [])
    else:
        alternatives = meta.get("alternatives", [])
        if not isinstance(alternatives, list) or alt_index >= len(alternatives):
            return None
        alternative = alternatives[alt_index]
        if not isinstance(alternative, dict):
            return None
        refs = alternative.get("source_refs", [])
    if not isinstance(refs, list) or ref_index >= len(refs):
        return None
    ref = refs[ref_index]
    return ref if isinstance(ref, dict) else None


def locate_bboxes(
    field_metadata: dict | list,
    pdf_bytes_map: dict[str, bytes],
) -> dict:
    """bbox対象フィールドのsource_refにbboxを付与して返す。

    Args:
        field_metadata: Gemini抽出結果の field_metadata
        pdf_bytes_map: {document_id: pdf_bytes}

    Returns:
        bbox付きの field_metadata (dict形式)
    """
    field_metadata = _map_field_metadata(field_metadata)

    # PDF Gemini bbox対象のsource_refsを (document_id, page) でグループ化
    page_groups: dict[tuple[str, int], dict[str, dict]] = {}
    candidate_map: dict[str, dict] = {}
    # 同一ページの同一locatorはGeminiに1回だけ聞き、結果を全refへ配る
    dedup_index: dict[tuple[str, int, str], dict] = {}
    candidate_count = 0
    skipped_low_quality = 0
    deduped_refs = 0
    for field_path, meta in field_metadata.items():
        if not isinstance(meta, dict):
            continue
        for alt_index, ref_index, ref in _iter_refs_for_bbox(meta):
            doc_id = ref.get("document_id", "")
            page_num = _page_number(ref.get("page"))
            text_quote = ref.get("text_quote", "")
            anchor_status = ref.get("anchor", {}).get("status")
            if ref.get("bbox") or anchor_status in ("resolved", "ambiguous"):
                continue
            if not text_quote or not doc_id:
                continue
            # PDFのみ対象
            if doc_id not in pdf_bytes_map:
                continue
            locator_text = _locator_text(text_quote)
            if _is_low_quality_locator(locator_text):
                skipped_low_quality += 1
                continue
            dedup_key = (doc_id, page_num, locator_text.lower())
            target: _BboxTarget = (field_path, alt_index, ref_index)
            existing = dedup_index.get(dedup_key)
            if existing is not None:
                existing["targets"].append(target)
                deduped_refs += 1
                continue
            candidate_id = f"candidate_{candidate_count:04d}"
            candidate_count += 1
            candidate = {
                "field_path": field_path,
                "targets": [target],
                "document_id": doc_id,
                "page": page_num,
                "text_quote": text_quote,
                "locator_text": locator_text,
            }
            page_groups.setdefault((doc_id, page_num), {})[candidate_id] = candidate
            candidate_map[candidate_id] = candidate
            dedup_index[dedup_key] = candidate

    if skipped_low_quality or deduped_refs:
        logger.info(
            "bbox_locator_metric event=candidates_filtered low_quality=%d deduped=%d",
            skipped_low_quality,
            deduped_refs,
        )

    if not page_groups:
        logger.info("bbox_locator_metric event=no_candidates fields=%d", len(field_metadata))
        return field_metadata

    # 1) 全ページの画像を並列レンダリング
    render_dpi = int(os.environ.get("BBOX_RENDER_DPI", "200"))
    render_workers = int(os.environ.get("BBOX_RENDER_WORKERS", "8"))
    started_at = time.monotonic()
    logger.info(
        "bbox_locator_metric event=started page_groups=%d candidates=%d render_workers=%d bbox_workers=%s",
        len(page_groups),
        len(candidate_map),
        render_workers,
        os.environ.get("BBOX_MAX_WORKERS", "8"),
    )

    def _render_page(key: tuple[str, int]) -> tuple[tuple[str, int], bytes | None]:
        doc_id, page_num = key
        pdf_bytes = pdf_bytes_map[doc_id]
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            try:
                page_idx = page_num - 1
                if page_idx < 0 or page_idx >= len(doc):
                    return key, None
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=render_dpi)
                return key, pix.tobytes("png")
            finally:
                doc.close()
        except Exception as exc:
            logger.warning(
                "bbox_locator_metric event=render_failed document_id=%s page=%d error_type=%s",
                doc_id,
                page_num,
                type(exc).__name__,
            )
            return key, None

    page_images: dict[tuple[str, int], bytes] = {}
    with ThreadPoolExecutor(max_workers=render_workers) as executor:
        for key, image_bytes in executor.map(_render_page, page_groups):
            if image_bytes is not None:
                page_images[key] = image_bytes
    logger.info(
        "bbox_locator_metric event=pages_rendered page_groups=%d rendered_pages=%d elapsed_ms=%d",
        len(page_groups),
        len(page_images),
        round((time.monotonic() - started_at) * 1000),
    )

    # 2) Gemini bbox 取得を並列実行
    max_workers = int(os.environ.get("BBOX_MAX_WORKERS", "8"))
    applied = 0

    def _fetch_bboxes(key: tuple[str, int]):
        doc_id, page_num = key
        candidates = page_groups[key]
        page_image_bytes = page_images[key]
        bboxes = get_bboxes_for_page(page_image_bytes, candidates)
        return key, bboxes

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_bboxes, key): key
            for key in page_images
        }
        for future in as_completed(futures):
            key = futures[future]
            doc_id, page_num = key
            try:
                _, bboxes = future.result()
            except Exception as e:
                logger.warning("Gemini bbox failed for %s page %d: %s", doc_id, page_num, e)
                continue

            # 結果を field_metadata に反映
            for candidate_id, bbox_coords in bboxes.items():
                candidate = candidate_map.get(candidate_id)
                if bbox_coords is None or not candidate:
                    continue
                if not isinstance(bbox_coords, list) or len(bbox_coords) != 4:
                    continue
                if candidate.get("document_id") != doc_id or candidate.get("page") != page_num:
                    continue
                for target in candidate["targets"]:
                    ref = _get_target_ref(field_metadata, target)
                    if ref is None:
                        continue
                    ref["bbox"] = {
                        "y_min": bbox_coords[0],
                        "x_min": bbox_coords[1],
                        "y_max": bbox_coords[2],
                        "x_max": bbox_coords[3],
                    }
                    applied += 1

    logger.info(
        "bbox_locator_metric event=completed page_groups=%d candidates=%d rendered_pages=%d applied_refs=%d elapsed_ms=%d",
        len(page_groups),
        len(candidate_map),
        len(page_images),
        applied,
        round((time.monotonic() - started_at) * 1000),
    )

    return field_metadata
