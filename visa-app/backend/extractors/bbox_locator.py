"""Gemini bbox取得: 対象フィールドのsource_refにbboxを付与する。"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymupdf

from .gemini import get_bboxes_for_page, _map_field_metadata

logger = logging.getLogger(__name__)

BBOX_TARGET_FIELDS = [
    # 申請人
    "applicant.name_roman",
    "applicant.nationality",
    "applicant.date_of_birth",
    "applicant.passport_number",
    # 雇用条件 (正規パス: employment_conditions)
    "employment_conditions.job_title",
    "employment_conditions.duties",
    "employment_conditions.monthly_salary",
    "employment_conditions.annual_salary",
    "employment_conditions.bonus",
    "employment_conditions.work_location",
    "employment_conditions.working_hours",
    "employment_conditions.joining_date",
    "employment_conditions.holidays",
    "employment_conditions.insurance",
    "employment_conditions.contract_period",
    "employment_conditions.contract_type",
    # 学歴
    "education.0.school_name",
    "education.0.major",
    # 所属機関
    "employer.company_name",
    "employer.capital",
    "employer.representative_name",
    "employer.business_category",
    "employer.business_type",
    "employer.corporate_number",
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
        return field_metadata

    # 1) 全ページの画像を一括レンダリング (CPU処理なので逐次で十分)
    page_images: dict[tuple[str, int], bytes] = {}
    for (doc_id, page_num) in page_groups:
        pdf_bytes = pdf_bytes_map[doc_id]
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page_idx = page_num - 1
        if page_idx < 0 or page_idx >= len(doc):
            doc.close()
            continue
        page = doc[page_idx]
        pix = page.get_pixmap(dpi=300)
        page_images[(doc_id, page_num)] = pix.tobytes("png")
        doc.close()

    # 2) Gemini bbox 取得を並列実行
    max_workers = int(os.environ.get("BBOX_MAX_WORKERS", "4"))

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

    return field_metadata
