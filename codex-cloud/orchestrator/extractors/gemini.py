"""Gemini 3 Flash structured extraction for visa application documents."""

import json
import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

from .prompt_template import build_extraction_prompt
from .types import ExtractionResult, OcrResult

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
BBOX_MODEL_NAME = os.environ.get("GEMINI_BBOX_MODEL", "gemini-3-flash-preview")



def _build_ocr_context(ocr_results: list[OcrResult]) -> str:
    sections = []
    for ocr in ocr_results:
        for page in ocr.pages:
            sections.append(
                f"--- document: {ocr.document_id}, page: {page.page_number} ---\n"
                f"{page.text}"
            )
    return "\n\n".join(sections)


def _get_client() -> genai.Client:
    return genai.Client()


def get_bboxes_for_page(
    page_image_bytes: bytes,
    field_quotes: dict[str, str],
) -> dict[str, list[int] | None]:
    """Gemini にページ画像を渡し、各text_quoteの bbox を取得。

    Returns: {field_path: [y_min, x_min, y_max, x_max]} (0-1000正規化座標)
    """
    if not field_quotes:
        return {}

    client = _get_client()

    prompt = (
        "この画像内で以下のテキストの位置を特定してください。\n"
        "各テキストについて、bounding box を [y_min, x_min, y_max, x_max] の形式で返してください。\n"
        "座標は 0-1000 の正規化座標です。\n"
        "見つからない場合は null を返してください。\n\n"
        "テキストリスト:\n"
    )
    for path, quote in field_quotes.items():
        prompt += f'- "{path}": "{quote}"\n'
    prompt += '\nJSON形式で返してください: {"field_path": [y_min, x_min, y_max, x_max] or null}'

    image_part = types.Part.from_bytes(data=page_image_bytes, mime_type="image/png")
    response = client.models.generate_content(
        model=BBOX_MODEL_NAME,
        contents=[image_part, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        logger.warning("Gemini bbox response parse error: %s", response.text[:200])
        return {}


def _call_gemini(client: genai.Client, contents: list, prompt: str) -> dict:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[*contents, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=65536,
        ),
    )
    # finish_reason を確認
    candidate = response.candidates[0] if response.candidates else None
    finish_reason = getattr(candidate, 'finish_reason', None) if candidate else None
    logger.debug("Gemini finish_reason: %s", finish_reason)

    raw_text = response.text
    logger.debug("Gemini response length: %d chars", len(raw_text))

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        from json_repair import repair_json
        repaired_text = repair_json(raw_text, return_objects=False)
        try:
            parsed = json.loads(repaired_text)
            logger.warning("Gemini response was truncated, repaired JSON (%d→%d chars)", len(raw_text), len(repaired_text))
        except json.JSONDecodeError as e:
            logger.error("Gemini JSON parse error: %s\nResponse head: %s", e, raw_text[:200])
            raise ValueError(f"Gemini returned invalid JSON: {e}") from e
    if isinstance(parsed, list) and len(parsed) == 1:
        parsed = parsed[0]

    # --- field_metadata 正規化 ---
    raw_fm = parsed.get("field_metadata", {})
    if isinstance(raw_fm, dict):
        for _fp, meta in raw_fm.items():
            refs = meta.get("source_refs", [])
            if not isinstance(refs, list):
                continue
            for ref in refs:
                # doc_id → document_id に統一
                if "doc_id" in ref and "document_id" not in ref:
                    ref["document_id"] = ref.pop("doc_id")
                # page: デフォルト1、文字列→整数
                if "page" not in ref:
                    ref["page"] = 1
                elif isinstance(ref["page"], str):
                    try:
                        ref["page"] = int(ref["page"])
                    except (ValueError, TypeError):
                        ref["page"] = 1
    elif isinstance(raw_fm, list):
        # リスト形式の場合も各エントリの source_refs を正規化
        for entry in raw_fm:
            if not isinstance(entry, dict):
                continue
            refs = entry.get("source_refs", [])
            if not isinstance(refs, list):
                continue
            for ref in refs:
                if "doc_id" in ref and "document_id" not in ref:
                    ref["document_id"] = ref.pop("doc_id")
                if "page" not in ref:
                    ref["page"] = 1
                elif isinstance(ref["page"], str):
                    try:
                        ref["page"] = int(ref["page"])
                    except (ValueError, TypeError):
                        ref["page"] = 1
        parsed["field_metadata"] = raw_fm

    # --- case_data の全フィールドに対して field_metadata を補完 ---
    fm = parsed.get("field_metadata")
    case_data = parsed.get("case_data")
    if isinstance(fm, dict) and isinstance(case_data, dict):
        for path in _flatten_keys(case_data):
            if path not in fm:
                fm[path] = {"source_refs": []}

    return parsed


def _flatten_keys(obj: dict, prefix: str = "") -> list[str]:
    """case_data のネストされたキーをドットパス表記でフラット化する。"""
    keys: list[str] = []
    for k, v in obj.items():
        path = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, path))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    keys.extend(_flatten_keys(item, f"{path}.{i}"))
                else:
                    keys.append(f"{path}.{i}")
        else:
            keys.append(path)
    return keys


def _map_field_metadata(
    raw_metadata: dict | list,
) -> dict:
    """Normalize field_metadata: convert list to dict, ensure all fields have source_refs."""
    # リスト形式の field_metadata を dict に変換
    if isinstance(raw_metadata, list):
        converted = {}
        for entry in raw_metadata:
            path = entry.get("field_path", entry.get("path", ""))
            if path:
                converted[path] = entry
        raw_metadata = converted

    return raw_metadata


def extract_text_only(
    ocr_results: list[OcrResult],
    case_meta: dict,
    documents: list[dict] | None = None,
    text_contents: list[tuple[str, str]] | None = None,
) -> ExtractionResult:
    """Pattern A: OCR text only."""
    prompt = build_extraction_prompt(case_meta, documents or [])
    ocr_context = _build_ocr_context(ocr_results)
    text_section = ""
    if text_contents:
        text_parts = []
        for doc_id, text in text_contents:
            text_parts.append(f"--- document: {doc_id} ---\n{text}")
        text_section = "\n\n## テキスト書類（xlsx/docx等）\n\n" + "\n\n".join(text_parts)
    full_prompt = f"{prompt}\n\n## 書類テキスト（OCR結果）\n\n{ocr_context}{text_section}"

    client = _get_client()
    raw = _call_gemini(client, [], full_prompt)

    field_metadata = _map_field_metadata(raw.get("field_metadata", {}))
    return ExtractionResult(
        case_data=raw.get("case_data", {}),
        review=raw.get("review", {}),
        field_metadata=field_metadata,
    )


def extract_pdf_direct(
    pdf_contents: list[tuple[str, bytes]],
    case_meta: dict,
    documents: list[dict] | None = None,
    text_contents: list[tuple[str, str]] | None = None,
) -> ExtractionResult:
    """Pattern B: PDF direct to Gemini."""
    prompt = build_extraction_prompt(case_meta, documents or [])
    parts = []
    # テキスト書類（xlsx, docx等）
    if text_contents:
        for doc_id, text in text_contents:
            parts.append(f"--- document: {doc_id} ---\n{text}")
    # PDF書類
    for doc_id, pdf_bytes in pdf_contents:
        parts.append(
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        )
        parts.append(f"(document_id: {doc_id})")

    client = _get_client()
    raw = _call_gemini(client, parts, prompt)

    return ExtractionResult(
        case_data=raw.get("case_data", {}),
        review=raw.get("review", {}),
        field_metadata=raw.get("field_metadata", {}),
    )


def extract_with_images(
    ocr_results: list[OcrResult],
    image_contents: list[tuple[str, bytes]],
    case_meta: dict,
    documents: list[dict] | None = None,
    text_contents: list[tuple[str, str]] | None = None,
) -> ExtractionResult:
    """Pattern C: OCR text + images."""
    prompt = build_extraction_prompt(case_meta, documents or [])
    ocr_context = _build_ocr_context(ocr_results)

    parts: list = []
    # テキスト書類（xlsx, docx等）
    if text_contents:
        for doc_id, text in text_contents:
            parts.append(f"--- document: {doc_id} ---\n{text}")
    parts.append(f"## 書類テキスト（OCR結果）\n\n{ocr_context}")
    for doc_id, img_bytes in image_contents:
        mime = "image/png" if img_bytes[:4] == b"\x89PNG" else "image/jpeg"
        parts.append(
            types.Part.from_bytes(data=img_bytes, mime_type=mime)
        )
        parts.append(f"(document_id: {doc_id})")

    client = _get_client()
    raw = _call_gemini(client, parts, prompt)

    field_metadata = _map_field_metadata(raw.get("field_metadata", {}))
    return ExtractionResult(
        case_data=raw.get("case_data", {}),
        review=raw.get("review", {}),
        field_metadata=field_metadata,
    )
