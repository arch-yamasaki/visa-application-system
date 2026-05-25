"""Gemini 3 Flash structured extraction for visa application documents."""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

from .prompt_template import build_extraction_prompt, build_scoped_prompt
from .types import ExtractionResult, OcrResult

# schema.py がまだ完成していない場合はコメントを外す
# from .schema import EXTRACTION_SCHEMA
try:
    from .schema import EXTRACTION_SCHEMA
except ImportError:
    EXTRACTION_SCHEMA = None
    logger.info("schema.py not found; response_schema will not be used")

try:
    from .schema import SCOPE_SCHEMAS
except ImportError:
    SCOPE_SCHEMAS = {}
    logger.info("SCOPE_SCHEMAS not found in schema.py; scoped extraction unavailable")

# Mapping from logical scope names to schema registry keys
_SCOPE_KEY_MAP = {
    "identity": "S1",
    "employer": "S2",
    "education": "S3",
    "review": "S6",
}

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
BBOX_MODEL_NAME = os.environ.get("GEMINI_BBOX_MODEL", "gemini-3-flash-preview")
GEMINI_HTTP_TIMEOUT_MS = int(os.environ.get("GEMINI_HTTP_TIMEOUT_MS", "300000"))
GEMINI_THINKING_LEVEL = os.environ.get("GEMINI_THINKING_LEVEL", "LOW").upper()

_SENTINEL = object()  # Default marker for _call_gemini schema parameter



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
    return genai.Client(
        http_options=types.HttpOptions(timeout=GEMINI_HTTP_TIMEOUT_MS)
    )


def _usage_count(usage, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) else None


def _thinking_config() -> types.ThinkingConfig | None:
    if not GEMINI_THINKING_LEVEL:
        return None
    level = getattr(types.ThinkingLevel, GEMINI_THINKING_LEVEL, None)
    if level is None:
        logger.warning("Unknown GEMINI_THINKING_LEVEL=%s; thinking_config disabled", GEMINI_THINKING_LEVEL)
        return None
    return types.ThinkingConfig(thinking_level=level)


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
            thinking_config=_thinking_config(),
        ),
    )

    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        logger.warning(
            "Gemini bbox response parse error response_chars=%d",
            len(response.text or ""),
        )
        return {}


def _call_gemini(
    client: genai.Client,
    contents: list,
    prompt: str,
    schema: dict | None = _SENTINEL,
    *,
    run_id: str | None = None,
    case_id: str | None = None,
    scope: str | None = None,
) -> dict:
    """Call Gemini API for structured extraction.

    Args:
        schema: JSON Schema for response_schema. Pass None to disable schema.
                Defaults to _SENTINEL which uses the legacy EXTRACTION_SCHEMA.
    """
    config_kwargs = dict(
        response_mime_type="application/json",
        temperature=0.0,
        max_output_tokens=65536,
    )
    thinking_config = _thinking_config()
    if thinking_config is not None:
        config_kwargs["thinking_config"] = thinking_config
    if schema is _SENTINEL:
        # Legacy path: use EXTRACTION_SCHEMA if available
        if EXTRACTION_SCHEMA is not None:
            config_kwargs["response_schema"] = EXTRACTION_SCHEMA
    elif schema is not None:
        config_kwargs["response_schema"] = schema

    started_at = time.monotonic()
    logger.info(
        "gemini_metric event=request_start %s",
        json.dumps(
            {
                "run_id": run_id,
                "case_id": case_id,
                "scope": scope,
                "model": MODEL_NAME,
                "parts": len(contents),
                "prompt_chars": len(prompt),
                "schema": schema is not None,
                "thinking_level": GEMINI_THINKING_LEVEL,
                "timeout_ms": GEMINI_HTTP_TIMEOUT_MS,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[*contents, prompt],
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as exc:
        logger.warning(
            "gemini_metric event=request_failed %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "case_id": case_id,
                    "scope": scope,
                    "model": MODEL_NAME,
                    "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                    "error_type": type(exc).__name__,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        raise
    elapsed_ms = round((time.monotonic() - started_at) * 1000)
    logger.info(
        "gemini_metric event=request_complete %s",
        json.dumps(
            {
                "run_id": run_id,
                "case_id": case_id,
                "scope": scope,
                "model": MODEL_NAME,
                "elapsed_ms": elapsed_ms,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    usage = getattr(response, "usage_metadata", None)
    if usage:
        logger.info(
            "gemini_metric event=token_usage %s",
            json.dumps(
                {
                    "run_id": run_id,
                    "case_id": case_id,
                    "scope": scope,
                    "model": MODEL_NAME,
                    "prompt_tokens": _usage_count(usage, "prompt_token_count"),
                    "candidate_tokens": _usage_count(usage, "candidates_token_count"),
                    "total_tokens": _usage_count(usage, "total_token_count"),
                    "thought_tokens": _usage_count(usage, "thoughts_token_count"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    # finish_reason を確認
    candidate = response.candidates[0] if response.candidates else None
    finish_reason = getattr(candidate, 'finish_reason', None) if candidate else None
    logger.debug("Gemini finish_reason: %s", finish_reason)
    logger.info(
        "gemini_metric event=finish_reason %s",
        json.dumps(
            {
                "run_id": run_id,
                "case_id": case_id,
                "scope": scope,
                "model": MODEL_NAME,
                "finish_reason": str(finish_reason) if finish_reason else None,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    if finish_reason and str(finish_reason).upper() in ("MAX_TOKENS", "2"):
        logger.warning(
            "Gemini response was truncated (finish_reason=%s). "
            "Output may be incomplete.", finish_reason
        )

    raw_text = response.text
    logger.debug("Gemini response length: %d chars", len(raw_text))

    parse_started_at = time.monotonic()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        from json_repair import repair_json
        repaired_text = repair_json(raw_text, return_objects=False)
        try:
            parsed = json.loads(repaired_text)
            logger.warning("Gemini response was truncated, repaired JSON (%d→%d chars)", len(raw_text), len(repaired_text))
        except json.JSONDecodeError as e:
            logger.error(
                "Gemini JSON parse error: %s response_chars=%d",
                e,
                len(raw_text),
            )
            raise ValueError(f"Gemini returned invalid JSON: {e}") from e
    if isinstance(parsed, list) and len(parsed) == 1:
        parsed = parsed[0]
    logger.info(
        "gemini_metric event=response_parsed %s",
        json.dumps(
            {
                "run_id": run_id,
                "case_id": case_id,
                "scope": scope,
                "response_chars": len(raw_text),
                "elapsed_ms": round((time.monotonic() - parse_started_at) * 1000),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )

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


def _deep_merge_case_data(target: dict, source: dict) -> dict:
    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge_case_data(target[key], value)
        else:
            target[key] = value
    return target


def _normalize_corporate_number(case_data: dict) -> None:
    """法人番号からハイフン・スペースを除去。"""
    employer = case_data.get("employer", {})
    cn = employer.get("corporate_number")
    if isinstance(cn, dict):  # FieldValue形式
        v = cn.get("value", "")
        if v:
            cn["value"] = re.sub(r'[\s\-]', '', v)
    elif isinstance(cn, str):
        employer["corporate_number"] = re.sub(r'[\s\-]', '', cn)


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

    # 法人番号の正規化（ハイフン・スペース除去）
    _normalize_corporate_number(raw_case_data)

    if _is_new_format(raw_case_data):
        # 新形式: case_data の FieldValue 構造から field_metadata と display 値を生成
        field_metadata = _extract_field_metadata(raw_case_data)
        display_case_data = _extract_display_values(raw_case_data)
        # source_refs の正規化
        _normalize_source_refs_in_metadata(field_metadata)
        _log_source_coverage(field_metadata, display_case_data)
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
        _log_source_coverage(field_metadata, raw_case_data)
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


def _log_source_coverage(field_metadata: dict, display_values: dict) -> None:
    """証跡充足率をログ出力し、値があるのに証跡がないフィールドをwarningで報告。"""
    total = len(field_metadata)
    if total == 0:
        return

    # display_values からフラットなパス→値を取得
    flat_values: dict[str, str] = {}
    def _flatten(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flatten(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _flatten(item, f"{prefix}.{i}")
        else:
            flat_values[prefix] = "" if obj is None else str(obj)
    _flatten(display_values)

    with_refs = 0
    missing_source_fields: list[str] = []
    for fp, meta in field_metadata.items():
        refs = meta.get("source_refs", [])
        if refs:
            with_refs += 1
        else:
            val = flat_values.get(fp, "")
            if val:
                missing_source_fields.append(fp)

    logger.info(
        "証跡充足率: %d/%d (%.1f%%)",
        with_refs, total, with_refs / total * 100,
    )
    for fp in missing_source_fields:
        logger.warning("値あり・証跡なし: %s", fp)


# ---------------------------------------------------------------------------
# Scoped (parallel) extraction — Phase 1
# ---------------------------------------------------------------------------

def extract_scoped(
    scope: str,
    client: genai.Client,
    contents: list,
    case_meta: dict,
    documents: list[dict],
    text_contents: list[tuple[str, str]] | None = None,
    run_id: str | None = None,
    case_id: str | None = None,
) -> dict:
    """Extract a single scope via Gemini (synchronous).

    Args:
        scope: Logical scope name ("identity", "employer", "education", "review").
        client: Gemini client instance.
        contents: Pre-built content parts (PDF bytes, text parts, etc.).
        case_meta: Case metadata dict.
        documents: Document manifest entries.
        text_contents: Optional text-extracted document contents.

    Returns:
        Parsed JSON dict from Gemini response for this scope.
    """
    schema_key = _SCOPE_KEY_MAP.get(scope)
    if not schema_key or schema_key not in SCOPE_SCHEMAS:
        raise ValueError(f"Unknown or unavailable scope: {scope!r}")

    schema = SCOPE_SCHEMAS[schema_key]
    prompt = build_scoped_prompt(scope, case_meta, documents)

    started_at = time.monotonic()
    logger.info(
        "gemini_metric event=scope_start %s",
        json.dumps(
            {
                "run_id": run_id,
                "case_id": case_id,
                "scope": scope,
                "parts": len(contents),
                "documents": len(documents),
                "prompt_chars": len(prompt),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    raw = _call_gemini(
        client,
        contents,
        prompt,
        schema=schema,
        run_id=run_id,
        case_id=case_id,
        scope=scope,
    )
    logger.info(
        "gemini_metric event=scope_complete %s",
        json.dumps(
            {
                "run_id": run_id,
                "case_id": case_id,
                "scope": scope,
                "elapsed_ms": round((time.monotonic() - started_at) * 1000),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    return raw


def extract_all_scopes(
    client: genai.Client,
    contents: list | dict[str, list],
    case_meta: dict,
    documents: list[dict] | dict[str, list[dict]],
    text_contents: list[tuple[str, str]] | None = None,
    run_id: str | None = None,
    case_id: str | None = None,
) -> ExtractionResult:
    """Run all extraction scopes in parallel, then review, then build result.

    Phase 1 scopes: identity (S1), employer (S2), education (S3) — parallel.
    Then review (S6) — sequential, using merged results as context.
    """
    extraction_scopes = ["identity", "employer", "education"]

    def contents_for(scope: str) -> list:
        if isinstance(contents, dict):
            return contents.get(scope) or contents.get("default") or []
        return contents

    def documents_for(scope: str) -> list[dict]:
        if isinstance(documents, dict):
            return documents.get(scope) or documents.get("default") or []
        return documents

    # Phase 1: S1, S2, S3 in parallel via ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            scope: executor.submit(
                extract_scoped, scope, client, contents_for(scope),
                case_meta, documents_for(scope), text_contents, run_id, case_id,
            )
            for scope in extraction_scopes
        }
        scope_results: dict[str, dict] = {}
        failed_scopes: dict[str, str] = {}
        for scope, future in futures.items():
            try:
                scope_results[scope] = future.result()
            except Exception as e:
                logger.warning("Scope %s failed: %s", scope, e, exc_info=True)
                scope_results[scope] = {}
                failed_scopes[scope] = f"{type(e).__name__}: {e}"

        if len(failed_scopes) == len(extraction_scopes):
            logger.info(
                "gemini_metric event=scopes_all_failed %s",
                json.dumps(
                    {
                        "run_id": run_id,
                        "case_id": case_id,
                        "failed_scopes": list(failed_scopes),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            raise RuntimeError(
                f"All extraction scopes failed: {', '.join(failed_scopes)}"
            )
        logger.info(
            "gemini_metric event=scopes_complete %s",
            json.dumps(
                {
                    "completed_scopes": [
                        scope for scope in extraction_scopes if scope not in failed_scopes
                    ],
                    "failed_scopes": list(failed_scopes),
                    "run_id": run_id,
                    "case_id": case_id,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    # Phase 2: Merge scope results into unified case_data
    merged_case_data: dict = {}
    for scope, result in scope_results.items():
        # Each scope returns a flat dict of sections (e.g. {"applicant": {...}, "passport": {...}})
        # or may be wrapped in "case_data" key — handle both
        data = result.get("case_data", result) if isinstance(result, dict) else {}
        _deep_merge_case_data(merged_case_data, data)

    # Phase 3: Review (S6) — sequential, with merged data as context
    review: dict = {}
    try:
        review_schema_key = _SCOPE_KEY_MAP["review"]
        review_schema = SCOPE_SCHEMAS.get(review_schema_key)
        review_prompt = build_scoped_prompt(
            "review", case_meta, documents_for("review"), extra_context=merged_case_data,
        )
        review = _call_gemini(
            client,
            contents_for("review"),
            review_prompt,
            schema=review_schema,
            run_id=run_id,
            case_id=case_id,
            scope="review",
        )
    except Exception as e:
        logger.warning("Review scope failed: %s", e)
        review = {}

    if failed_scopes:
        review.setdefault("validation_errors", [])
        for scope, error in failed_scopes.items():
            review["validation_errors"].append(
                f"抽出scope `{scope}` が失敗しました。人間レビューで不足項目を確認してください。原因: {error}"
            )
        review.setdefault("findings", [])
        review["findings"].append(
            "一部の抽出scopeが失敗したため、抽出結果は部分的です。"
        )

    # Phase 4: Build ExtractionResult via existing _build_extraction_result
    full_data = {"case_data": merged_case_data, "review": review}
    return _build_extraction_result(full_data)


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
