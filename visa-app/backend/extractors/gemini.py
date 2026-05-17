"""Gemini 3 Flash structured extraction for visa application documents."""

import json
import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

from .prompt_template import build_extraction_prompt
from .types import ExtractionResult, OcrResult

# schema.py がまだ完成していない場合はコメントを外す
# from .schema import EXTRACTION_SCHEMA
try:
    from .schema import EXTRACTION_SCHEMA
except ImportError:
    EXTRACTION_SCHEMA = None
    logger.info("schema.py not found; response_schema will not be used")

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
    config_kwargs = dict(
        response_mime_type="application/json",
        temperature=0.0,
        max_output_tokens=65536,
    )
    if EXTRACTION_SCHEMA is not None:
        config_kwargs["response_schema"] = EXTRACTION_SCHEMA

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[*contents, prompt],
        config=types.GenerateContentConfig(**config_kwargs),
    )
    # finish_reason を確認
    candidate = response.candidates[0] if response.candidates else None
    finish_reason = getattr(candidate, 'finish_reason', None) if candidate else None
    logger.debug("Gemini finish_reason: %s", finish_reason)
    if finish_reason and str(finish_reason).upper() in ("MAX_TOKENS", "2"):
        logger.warning(
            "Gemini response was truncated (finish_reason=%s). "
            "Output may be incomplete.", finish_reason
        )

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

    # --- employment フィールドパス正規化 (employment_terms/contract → conditions) ---
    parsed = _normalize_employment_keys(parsed)

    return parsed


# ---------------------------------------------------------------------------
# 互換レイヤー: 新形式 case_data → field_metadata / display_case_data
# ---------------------------------------------------------------------------

def _extract_field_metadata(case_data: dict) -> dict:
    """新形式のcase_dataからfield_metadataを自動生成（後方互換用）。"""
    metadata = {}
    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            if "value" in obj and "source_refs" in obj:
                metadata[prefix] = {
                    "source_refs": obj.get("source_refs", []),
                    "confidence": max(
                        (r.get("confidence", 0) for r in obj.get("source_refs", [])),
                        default=None,
                    ),
                    "human_edited": False,
                }
                return
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                walk(v, path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{prefix}.{i}")
    walk(case_data)
    return metadata


def _extract_display_values(case_data: dict) -> dict:
    """FieldValue構造から value のみ取り出した従来形式の case_data を返す。"""
    def unwrap(obj):
        if isinstance(obj, dict):
            if "value" in obj and "source_refs" in obj:
                return obj["value"]
            return {k: unwrap(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [unwrap(item) for item in obj]
        return obj
    return unwrap(case_data)


def _is_new_format(case_data: dict) -> bool:
    """case_data が新形式（FieldValue 構造）かどうかを判定する。

    新形式: 末端が {value, source_refs} または {value, document_id, ...} の dict。
    旧形式: 末端がスカラ値（str, int 等）。
    """
    def check(obj):
        if isinstance(obj, dict):
            if "value" in obj and "source_refs" in obj:
                return True
            # Compact source-string format from current schema.py
            if "value" in obj and "source" in obj:
                return True
            # Flattened FieldValue format (legacy)
            if "value" in obj and "document_id" in obj and "text_quote" in obj:
                return True
            for v in obj.values():
                result = check(v)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = check(item)
                if result is not None:
                    return result
        return None
    result = check(case_data)
    return result is True


# --- employment フィールドパス正規化 ---
_EMPLOYMENT_ALIASES = ("employment_terms", "employment_contract")
_EMPLOYMENT_CANONICAL = "employment_conditions"


def _normalize_employment_keys(parsed: dict) -> dict:
    """Rename employment_terms / employment_contract → employment_conditions
    in both case_data and field_metadata to ensure consistent field paths.

    新形式（FieldValue 構造）でも旧形式でも動作する。
    """
    # --- case_data ---
    case_data = parsed.get("case_data")
    if isinstance(case_data, dict):
        for alias in _EMPLOYMENT_ALIASES:
            if alias in case_data and _EMPLOYMENT_CANONICAL not in case_data:
                case_data[_EMPLOYMENT_CANONICAL] = case_data.pop(alias)
            elif alias in case_data:
                # merge into canonical, alias values as fallback
                canonical = case_data[_EMPLOYMENT_CANONICAL]
                alias_data = case_data.pop(alias)
                if isinstance(canonical, dict) and isinstance(alias_data, dict):
                    for k, v in alias_data.items():
                        if k not in canonical or not canonical[k]:
                            canonical[k] = v

    # --- field_metadata (旧形式の場合のみ) ---
    fm = parsed.get("field_metadata")
    if isinstance(fm, dict):
        keys_to_rename = []
        for key in list(fm.keys()):
            for alias in _EMPLOYMENT_ALIASES:
                if key.startswith(alias + "."):
                    new_key = _EMPLOYMENT_CANONICAL + key[len(alias):]
                    keys_to_rename.append((key, new_key))
                elif key == alias:
                    keys_to_rename.append((key, _EMPLOYMENT_CANONICAL))
        for old_key, new_key in keys_to_rename:
            if new_key not in fm:
                fm[new_key] = fm.pop(old_key)
            else:
                fm.pop(old_key)

    return parsed


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


def _parse_source_string(source: str) -> dict | None:
    """Parse a 'document_id|page|text_quote|confidence' string into a source_ref dict.

    Returns None if the source string is empty or unparseable.
    """
    if not source or not source.strip():
        return None
    parts = source.split("|", 3)  # max 4 parts
    if len(parts) < 4:
        # Fallback: treat whole string as text_quote
        return {
            "document_id": "",
            "page": 1,
            "text_quote": source.strip(),
            "confidence": 0.5,
        }
    try:
        page = int(parts[1].strip())
    except (ValueError, TypeError):
        page = 1
    try:
        confidence = float(parts[3].strip())
    except (ValueError, TypeError):
        confidence = 0.5
    return {
        "document_id": parts[0].strip(),
        "page": page,
        "text_quote": parts[2].strip(),
        "confidence": confidence,
    }


def _unflatten_field_values(obj):
    """Convert compact FieldValue {value, source} into standard
    {value, source_refs: [{document_id, page, text_quote, confidence}]} format.

    Also handles the older flattened format {value, document_id, page, ...}.
    """
    if isinstance(obj, dict):
        # Compact source-string format from current schema.py
        if "value" in obj and "source" in obj and "source_refs" not in obj:
            ref = _parse_source_string(obj.get("source", ""))
            source_refs = [ref] if ref else []
            return {"value": obj.get("value"), "source_refs": source_refs}
        # Flattened FieldValue format (legacy)
        if "value" in obj and "document_id" in obj and "text_quote" in obj and "source_refs" not in obj:
            ref = {
                "document_id": obj.get("document_id", ""),
                "page": obj.get("page", 1),
                "text_quote": obj.get("text_quote", ""),
                "confidence": obj.get("confidence", 0.0),
            }
            source_refs = [ref] if obj.get("document_id") else []
            return {"value": obj.get("value"), "source_refs": source_refs}
        return {k: _unflatten_field_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_unflatten_field_values(item) for item in obj]
    return obj


def _build_extraction_result(parsed: dict) -> ExtractionResult:
    """Gemini のパース結果から ExtractionResult を構築する。

    新形式（FieldValue 構造）と旧形式の両方に対応。
    フラット化された FieldValue も source_refs 形式に正規化する。
    """
    raw_case_data = parsed.get("case_data", {})
    # Unflatten if needed (schema.py outputs flattened format)
    raw_case_data = _unflatten_field_values(raw_case_data)
    parsed["case_data"] = raw_case_data

    if _is_new_format(raw_case_data):
        # 新形式: case_data の FieldValue 構造から field_metadata と display 値を生成
        field_metadata = _extract_field_metadata(raw_case_data)
        display_case_data = _extract_display_values(raw_case_data)
        # source_refs の正規化
        _normalize_source_refs_in_metadata(field_metadata)
        return ExtractionResult(
            case_data=raw_case_data,
            display_case_data=display_case_data,
            review=parsed.get("review", {}),
            field_metadata=field_metadata,
        )
    else:
        # 旧形式（response_schema 未適用時のフォールバック）
        # field_metadata の正規化
        raw_fm = parsed.get("field_metadata", {})
        if isinstance(raw_fm, dict):
            _normalize_source_refs_in_metadata(raw_fm)
        elif isinstance(raw_fm, list):
            for entry in raw_fm:
                if isinstance(entry, dict):
                    _normalize_source_refs_in_entry(entry)
            parsed["field_metadata"] = raw_fm
        field_metadata = _map_field_metadata(parsed.get("field_metadata", {}))
        return ExtractionResult(
            case_data=raw_case_data,
            display_case_data=raw_case_data,  # 旧形式はそのまま
            review=parsed.get("review", {}),
            field_metadata=field_metadata,
        )


def _normalize_source_refs_in_metadata(fm: dict) -> None:
    """field_metadata 内の source_refs を正規化する。"""
    for _fp, meta in fm.items():
        if not isinstance(meta, dict):
            continue
        _normalize_source_refs_in_entry(meta)


def _normalize_source_refs_in_entry(meta: dict) -> None:
    """source_refs の各 ref を正規化する。"""
    refs = meta.get("source_refs", [])
    if not isinstance(refs, list):
        return
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

    return _build_extraction_result(raw)


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

    return _build_extraction_result(raw)


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

    return _build_extraction_result(raw)
