"""Gemini cell selector: ambiguousなxlsx anchorの候補セルから意味で1つ選ぶ。

決定的resolver(文字列一致)が列挙した候補の中からしか選ばせないため、
存在しないセルを指すことは構造的にできない。判断できないものは
ambiguous(candidates付き)のまま残す。
"""

import logging
from collections import defaultdict

from .anchor_resolver import _iter_all_refs, _preferred_sheets
from .gemini import _map_field_metadata, select_anchor_cells

logger = logging.getLogger(__name__)

# シート内容のプロンプト上限。intakeシートは数千chars程度で収まる想定の防御値。
_MAX_CONTEXT_CHARS = 20000


def _sheet_context_text(items: list[dict], sheet_names: set[str]) -> str:
    """候補が載っているシートだけを、セル番地付きテキストに整形する。"""
    rows: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for item in items:
        sheet = item.get("sheet_name")
        if sheet in sheet_names and str(item.get("text") or "").strip():
            rows[(sheet, int(item.get("row") or 0))].append(item)

    lines: list[str] = []
    current_sheet = None
    for (sheet, _row), row_items in sorted(rows.items()):
        if sheet != current_sheet:
            lines.append(f"--- sheet: {sheet} ---")
            current_sheet = sheet
        cells = " | ".join(
            f"{item.get('cell')}={str(item.get('text')).strip()}"
            for item in sorted(row_items, key=lambda x: int(x.get("col") or 0))
        )
        lines.append(cells)
    text = "\n".join(lines)
    if len(text) > _MAX_CONTEXT_CHARS:
        logger.info(
            "cell_selector_metric event=context_truncated chars=%d", len(text)
        )
        text = text[:_MAX_CONTEXT_CHARS]
    return text


def select_ambiguous_cells(
    field_metadata: dict | list,
    xlsx_cell_indexes: dict[str, list[dict]],
) -> dict:
    """ambiguousなxlsx anchorをGemini選択器で解決して返す。

    選択された場合は resolved(resolver_type=gemini_cell_select)へ昇格し、
    監査用に candidates と select_reason を保持する。
    """
    field_metadata = _map_field_metadata(field_metadata)
    if not xlsx_cell_indexes:
        return field_metadata

    # document_idごとに選択対象を集める。
    # 申請人シート(resolvedが集中するシート)が分かっている場合、候補をそのシートに限定する。
    # 申請人シート上に候補がない選択は、他人のセルを選ばせないため対象外にする。
    preferred = _preferred_sheets(field_metadata)
    selections_by_doc: dict[str, dict[str, dict]] = defaultdict(dict)
    selection_refs: dict[str, dict] = {}
    selection_count = 0
    skipped_off_sheet = 0
    for field_path, meta in field_metadata.items():
        if not isinstance(meta, dict):
            continue
        for ref in _iter_all_refs(meta):
            anchor = ref.get("anchor") or {}
            if anchor.get("type") != "xlsx_cell" or anchor.get("status") != "ambiguous":
                continue
            candidates = anchor.get("candidates") or []
            candidate_ids = [c.get("anchor_id") for c in candidates if c.get("anchor_id")]
            doc_id = str(ref.get("document_id") or "")
            if doc_id not in xlsx_cell_indexes:
                continue
            preferred_sheet = preferred.get(doc_id)
            if preferred_sheet:
                on_sheet = [
                    anchor_id
                    for anchor_id in candidate_ids
                    if anchor_id.startswith(f"{preferred_sheet}!")
                ]
                if not on_sheet:
                    skipped_off_sheet += 1
                    continue
                candidate_ids = on_sheet
            if len(candidate_ids) < 2:
                continue
            selection_id = f"selection_{selection_count:04d}"
            selection_count += 1
            selections_by_doc[doc_id][selection_id] = {
                "field_path": field_path,
                "text_quote": str(ref.get("text_quote") or "")[:80],
                "candidate_anchor_ids": candidate_ids,
            }
            selection_refs[selection_id] = ref

    if skipped_off_sheet:
        logger.info(
            "cell_selector_metric event=skipped_off_sheet count=%d", skipped_off_sheet
        )
    if not selections_by_doc:
        return field_metadata

    applied = invalid = declined = 0
    for doc_id, selections in selections_by_doc.items():
        items = xlsx_cell_indexes[doc_id]
        sheet_names = {
            anchor_id.split("!", 1)[0]
            for selection in selections.values()
            for anchor_id in selection["candidate_anchor_ids"]
            if "!" in anchor_id
        }
        context_text = _sheet_context_text(items, sheet_names)
        try:
            results = select_anchor_cells(context_text, selections)
        except Exception as exc:
            logger.warning(
                "cell_selector_metric event=select_failed document_id=%s error_type=%s",
                doc_id,
                type(exc).__name__,
            )
            continue

        for selection_id, selection in selections.items():
            result = results.get(selection_id)
            if not isinstance(result, dict) or not result.get("anchor_id"):
                declined += 1
                continue
            anchor_id = result["anchor_id"]
            if anchor_id not in selection["candidate_anchor_ids"]:
                invalid += 1
                continue
            ref = selection_refs[selection_id]
            anchor = ref["anchor"]
            chosen = next(
                c for c in anchor["candidates"] if c.get("anchor_id") == anchor_id
            )
            new_anchor = {
                "type": "xlsx_cell",
                "status": "resolved",
                "resolver_type": "gemini_cell_select",
                "match_count": anchor.get("match_count", len(anchor["candidates"])),
                # 監査用: 候補と選択理由を残す(UIの選び直しにも使える)
                "candidates": anchor["candidates"],
                "select_reason": str(result.get("reason") or "")[:60],
            }
            new_anchor.update(chosen)
            ref["anchor"] = new_anchor
            applied += 1

    logger.info(
        "cell_selector_metric event=completed selections=%d applied=%d declined=%d invalid=%d",
        selection_count,
        applied,
        declined,
        invalid,
    )
    return field_metadata
