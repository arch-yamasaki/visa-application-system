"""Gemini bbox取得: 対象フィールドのsource_refにbboxを付与する。"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymupdf

from .gemini import get_bboxes_for_page, _map_field_metadata

logger = logging.getLogger(__name__)

BBOX_TARGET_FIELDS = [
    "applicant.birth_date",
    "applicant.home_country_address",
    "applicant.marital_status",
    "applicant.name_roman",
    "applicant.nationality_region",
    "applicant.occupation",
    "applicant.birth_place",
    "applicant.passport.expiry_date",
    "applicant.passport.number",
    "applicant.family.has_accompanying_members",
    "applicant.immigration_history.entries_count",
    "applicant.immigration_history.criminal_record",
    "applicant.immigration_history.deportation_or_departure_order",
    "applicant.immigration_history.has_entries",
    "applicant.immigration_history.prior_coe_applications.has_history",
    "applicant.immigration_history.prior_coe_applications.count",
    "applicant.education.0.graduation_date",
    "applicant.education.0.level",
    "applicant.education.0.school_name",
    "applicant.education.0.major_field",
    "entry_plan.planned_entry_date",
    "entry_plan.planned_period_months",
    "entry_plan.planned_period_years",
    "entry_plan.purpose_of_entry",
    "employer.address",
    "employer.annual_sales_jpy",
    "employer.capital_jpy",
    "employer.corporate_number",
    "employer.employee_count",
    "employer.has_corporate_number",
    "employer.industry_primary",
    "employer.name",
    "employer.office_name",
    "employer.phone",
    "employer.postal_code",
    "employment.contract_type",
    "employment.employment_period_months",
    "employment.employment_period_type",
    "employment.employment_period_years",
    "employment.experience_months",
    "employment.has_position",
    "employment.job_category_primary",
    "employment.joining_date",
    "employment.monthly_salary",
    "employment.position_title",
    "employment.activity_details",
]


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

    # bbox対象フィールドのsource_refsを (document_id, page) でグループ化
    page_groups: dict[tuple[str, int], dict[str, str]] = {}
    for field_path in BBOX_TARGET_FIELDS:
        meta = field_metadata.get(field_path)
        if not meta:
            continue
        for ref in meta.get("source_refs", []):
            doc_id = ref.get("document_id", "")
            page_num = ref.get("page", 1)
            text_quote = ref.get("text_quote", "")
            if not text_quote or not doc_id:
                continue
            # PDFのみ対象
            if doc_id not in pdf_bytes_map:
                continue
            key = (doc_id, page_num)
            if key not in page_groups:
                page_groups[key] = {}
            page_groups[key][field_path] = text_quote

    if not page_groups:
        logger.info("bbox_locator_metric event=no_candidates fields=%d", len(field_metadata))
        return field_metadata

    # 1) 全ページの画像を並列レンダリング
    render_dpi = int(os.environ.get("BBOX_RENDER_DPI", "200"))
    render_workers = int(os.environ.get("BBOX_RENDER_WORKERS", "8"))
    started_at = time.monotonic()
    logger.info(
        "bbox_locator_metric event=started page_groups=%d render_workers=%d bbox_workers=%s",
        len(page_groups),
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
        field_quotes = page_groups[key]
        page_image_bytes = page_images[key]
        bboxes = get_bboxes_for_page(page_image_bytes, field_quotes)
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
            for field_path, bbox_coords in bboxes.items():
                if bbox_coords is None or field_path not in field_metadata:
                    continue
                if not isinstance(bbox_coords, list) or len(bbox_coords) != 4:
                    continue
                for ref in field_metadata[field_path].get("source_refs", []):
                    if ref.get("document_id") == doc_id and ref.get("page", 1) == page_num:
                        ref["bbox"] = {
                            "y_min": bbox_coords[0],
                            "x_min": bbox_coords[1],
                            "y_max": bbox_coords[2],
                            "x_max": bbox_coords[3],
                        }
                        applied += 1

    logger.info(
        "bbox_locator_metric event=completed page_groups=%d rendered_pages=%d applied_refs=%d elapsed_ms=%d",
        len(page_groups),
        len(page_images),
        applied,
        round((time.monotonic() - started_at) * 1000),
    )

    return field_metadata
