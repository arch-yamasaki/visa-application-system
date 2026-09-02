"""Gemini 3.7 Flash structured extraction for visa application documents."""

import json
import logging
import math
import os
import re
import time
import copy
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)

from .prompt_template import build_extraction_prompt, build_scoped_prompt
from .types import ExtractionResult, OcrResult

# schema.py がまだ完成していない場合はコメントを外す
# from .schema import EXTRACTION_SCHEMA
try:
    from .schema import EXTRACTION_SCHEMA, to_response_json_schema
except ImportError:
    EXTRACTION_SCHEMA = None
    to_response_json_schema = None
    logger.info("schema.py not found; response_schema will not be used")

try:
    from .schema import SCOPE_SCHEMAS
except ImportError:
    SCOPE_SCHEMAS = {}
    logger.info("SCOPE_SCHEMAS not found in schema.py; scoped extraction unavailable")

# Mapping from logical scope names to schema registry keys
_SCOPE_KEY_MAP = {
    "applicant_identity": "applicant_identity",
    "entry_plan": "entry_plan",
    "immigration_history": "immigration_history",
    "education": "education",
    "employment_history": "employment_history",
    "employer": "employer",
    "employment": "employment",
    "review": "review",
}

EXTRACTION_SCOPES = [
    "applicant_identity",
    "entry_plan",
    "immigration_history",
    "education",
    "employment_history",
    "employer",
    "employment",
]

DEFAULT_GEMINI_MODEL = "gemini-3.7-flash"
MODEL_NAME = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
GEMINI_HTTP_TIMEOUT_MS = int(os.environ.get("GEMINI_HTTP_TIMEOUT_MS", "300000"))
GEMINI_THINKING_LEVEL = os.environ.get("GEMINI_THINKING_LEVEL", "LOW").upper()
GEMINI_MAX_ATTEMPTS = 3
GEMINI_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
PASSPORT_IDENTITY_MIN_CONFIDENCE = 0.8
PASSPORT_IDENTITY_FIELDS = {
    "name_roman": ("applicant.name_roman", "氏名（ローマ字）"),
    "birth_date": ("applicant.birth_date", "生年月日"),
}
_ENGLISH_MONTHS = {
    "JAN": 1, "JANUARY": 1,
    "FEB": 2, "FEBRUARY": 2,
    "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4,
    "MAY": 5,
    "JUN": 6, "JUNE": 6,
    "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8,
    "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10,
    "NOV": 11, "NOVEMBER": 11,
    "DEC": 12, "DECEMBER": 12,
}

_SENTINEL = object()  # Default marker for _call_gemini schema parameter

_SEX_INTERNAL_VALUES = {
    "male": "male",
    "m": "male",
    "man": "male",
    "男": "male",
    "男性": "male",
    "男male": "male",
    "male男": "male",
    "female": "female",
    "f": "female",
    "woman": "female",
    "女": "female",
    "女性": "female",
    "女female": "female",
    "female女": "female",
}

_MARITAL_STATUS_INTERNAL_VALUES = {
    "single": "single",
    "unmarried": "single",
    "none": "single",
    "no": "single",
    "n": "single",
    "無": "single",
    "なし": "single",
    "無し": "single",
    "未婚": "single",
    "独身": "single",
    "無single": "single",
    "single無": "single",
    "married": "married",
    "yes": "married",
    "y": "married",
    "有": "married",
    "あり": "married",
    "既婚": "married",
    "有married": "married",
    "married有": "married",
}

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


def _gemini_error_status(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _is_retryable_gemini_error(exc: Exception) -> bool:
    status = _gemini_error_status(exc)
    if status in GEMINI_RETRYABLE_STATUS_CODES:
        return True
    if isinstance(exc, genai_errors.APIError):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    class_name = type(exc).__name__.lower()
    return "timeout" in class_name or "connection" in class_name


def _safe_gemini_error_label(exc: Exception) -> str:
    status = _gemini_error_status(exc)
    if status is None:
        return type(exc).__name__
    return f"{type(exc).__name__} status={status}"


def _log_gemini_request_error(
    event: str,
    exc: Exception,
    attempt: int,
    *,
    scope: str | None,
    started_at: float,
) -> None:
    logger.warning(
        "gemini_metric event=%s %s",
        event,
        json.dumps(
            {
                "attempt": attempt,
                "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                "error_type": type(exc).__name__,
                "model": MODEL_NAME,
                "scope": scope,
                "status": _gemini_error_status(exc),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


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
        schema: Extraction schema. Pass None to disable structured output.
                Defaults to _SENTINEL which uses the legacy EXTRACTION_SCHEMA.
    """
    config_kwargs = dict(
        response_mime_type="application/json",
        max_output_tokens=65536,
    )
    thinking_config = _thinking_config()
    if thinking_config is not None:
        config_kwargs["thinking_config"] = thinking_config
    if schema is _SENTINEL:
        # Legacy path: use EXTRACTION_SCHEMA if available
        if EXTRACTION_SCHEMA is not None:
            config_kwargs["response_json_schema"] = to_response_json_schema(EXTRACTION_SCHEMA)
    elif schema is not None:
        config_kwargs["response_json_schema"] = to_response_json_schema(schema)

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
    for attempt in range(1, GEMINI_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[*contents, prompt],
                config=types.GenerateContentConfig(**config_kwargs),
            )
            break
        except Exception as exc:
            retryable = _is_retryable_gemini_error(exc)
            has_attempt_left = attempt < GEMINI_MAX_ATTEMPTS
            if retryable and has_attempt_left:
                _log_gemini_request_error(
                    "request_retry",
                    exc,
                    attempt,
                    scope=scope,
                    started_at=started_at,
                )
                time.sleep(1.0 * (2 ** (attempt - 1)))
                continue
            _log_gemini_request_error(
                "request_failed",
                exc,
                attempt,
                scope=scope,
                started_at=started_at,
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
                "attempt": attempt,
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
    """FieldValue case_dataからfield_metadataを生成する。"""
    metadata = {}
    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            if "value" in obj and "source_refs" in obj:
                alternatives = obj.get("alternatives")
                entry = {
                    "source_refs": obj.get("source_refs", []),
                    "confidence": max(
                        (r.get("confidence", 0) for r in obj.get("source_refs", [])),
                        default=None,
                    ),
                    "has_value": obj.get("value") not in (None, "") or any(
                        isinstance(alternative, dict)
                        and alternative.get("value") not in (None, "")
                        for alternative in alternatives or []
                    ),
                    "human_edited": False,
                }
                if obj.get("origin"):
                    entry["origin"] = obj["origin"]
                if alternatives:
                    entry["alternatives"] = alternatives
                metadata[prefix] = entry
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
    """case_data が FieldValue 構造かどうかを判定する。"""
    def check(obj):
        if isinstance(obj, dict):
            if "value" in obj and "source_ref" in obj:
                return True
            if "value" in obj and "source_refs" in obj:
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


def _pop_passport_identity_candidates(identity_result: dict) -> list:
    """Remove identity-page detection metadata before canonical data merging.

    The response schema defines this as a sibling of ``applicant``.  The
    defensive nested pop keeps a malformed/legacy ``case_data`` wrapper from
    leaking the helper key into persisted canonical case_data.
    """
    if not isinstance(identity_result, dict):
        return []

    candidates = identity_result.pop("passport_identity_page_candidates", None)
    wrapped = identity_result.get("case_data")
    if isinstance(wrapped, dict):
        nested = wrapped.pop("passport_identity_page_candidates", None)
        if candidates is None:
            candidates = nested
    return candidates if isinstance(candidates, list) else []


def _document_page_count(document: dict) -> int | None:
    """Return manifest page count when a producer has supplied one."""
    for key in ("page_count", "pages"):
        value = document.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return None


def _normalize_passport_identity_candidates(
    raw_candidates: list,
    documents: list[dict],
) -> tuple[list[dict], int]:
    """Validate, normalize and de-duplicate document/page candidates."""
    manifests = {
        str(document.get("document_id") or "").strip(): document
        for document in documents
        if isinstance(document, dict) and str(document.get("document_id") or "").strip()
    }
    normalized: list[dict] = []
    seen: set[tuple[str, int]] = set()
    invalid_count = 0

    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            invalid_count += 1
            continue
        document_id = str(candidate.get("document_id") or "").strip()
        raw_page = candidate.get("page")
        try:
            if isinstance(raw_page, bool) or (
                isinstance(raw_page, float) and not raw_page.is_integer()
            ):
                raise ValueError
            page = int(raw_page)
        except (TypeError, ValueError, OverflowError):
            page = 0
        document = manifests.get(document_id)
        page_count = _document_page_count(document) if document else None
        document_kind = str(document.get("document_kind") or "") if document else ""
        if (
            not document
            or document_kind not in {"pdf", "image"}
            or page_count is None
            or page <= 0
            or page > page_count
        ):
            invalid_count += 1
            continue
        key = (document_id, page)
        if key in seen:
            continue
        raw_confidence = candidate.get("confidence", 0)
        try:
            if isinstance(raw_confidence, bool):
                raise ValueError
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            invalid_count += 1
            continue
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            invalid_count += 1
            continue
        normalized.append(
            {
                "document_id": document_id,
                "page": page,
                "confidence": confidence,
                "mrz_detected": candidate.get("mrz_detected") is True,
            }
        )
        seen.add(key)
    return normalized, invalid_count


def _empty_source_ref() -> dict:
    return {"document_id": "", "page": 0, "text_quote": "", "confidence": 0, "locations": []}


def _withhold_field_value(field_value: dict) -> bool:
    """Clear an unverified primary value while retaining it for human adoption."""
    if not isinstance(field_value, dict):
        return False
    value = field_value.get("value")
    if value is None or value == "":
        return False

    source_ref = field_value.get("source_ref")
    alternatives = field_value.get("alternatives")
    retained = []
    if isinstance(source_ref, dict):
        retained_value = {"value": value, "source_ref": copy.deepcopy(source_ref)}
        if field_value.get("origin"):
            retained_value["origin"] = field_value["origin"]
        retained.append(retained_value)
    if isinstance(alternatives, list):
        retained.extend(copy.deepcopy(alternatives))

    field_value["value"] = ""
    field_value["source_ref"] = _empty_source_ref()
    if retained:
        # The normal compatibility layer also removes same-value duplicates
        # and caps alternatives; keeping two here preserves its public limit.
        field_value["alternatives"] = retained[:2]
    else:
        field_value.pop("alternatives", None)
    return True


def _source_matches_passport_page(field_value: dict, candidate: dict) -> bool:
    if not isinstance(field_value, dict) or not field_value.get("value"):
        return False
    source_ref = field_value.get("source_ref")
    if not isinstance(source_ref, dict):
        return False
    try:
        page = int(source_ref.get("page"))
    except (TypeError, ValueError):
        return False
    return (
        str(source_ref.get("document_id") or "").strip() == candidate["document_id"]
        and page == candidate["page"]
    )


def _source_looks_like_mrz(field_value: dict) -> bool:
    """Reject source quotes that look like machine-readable-zone text."""
    if not isinstance(field_value, dict):
        return False
    source_ref = field_value.get("source_ref")
    if not isinstance(source_ref, dict):
        return False
    quote = unicodedata.normalize(
        "NFKC", str(source_ref.get("text_quote") or "")
    ).upper()
    compact = re.sub(r"\s+", "", quote)
    return compact.startswith("P<") or compact.count("<") >= 2


def _iso_birth_date(value) -> str | None:
    """Strictly normalize an unambiguous four-digit-year birth date."""
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw:
        return None

    year_first = re.fullmatch(
        r"(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})",
        raw,
    )
    if year_first:
        year, month, day = (int(part) for part in year_first.groups())
    else:
        month_name = re.fullmatch(
            r"(\d{1,2})\s*(?:[-/.]|\s)\s*([A-Za-z]{3,9})\.?,?"
            r"\s*(?:[-/.]|\s)\s*(\d{4})",
            raw,
        )
        if month_name:
            day_text, month_text, year_text = month_name.groups()
            month = _ENGLISH_MONTHS.get(month_text.upper())
            if month is None:
                return None
            year, day = int(year_text), int(day_text)
        else:
            year_last = re.fullmatch(
                r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})",
                raw,
            )
            if not year_last:
                return None
            first, second, year_text = (int(part) for part in year_last.groups())
            year = year_text
            if first > 12 >= second:
                day, month = first, second
            elif second > 12 >= first:
                month, day = first, second
            else:
                # Both DMY and MDY are plausible; do not guess.
                return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize_passport_birth_date_field(field_value: dict) -> bool:
    """Normalize only FieldValue.value; source_ref keeps the original quote."""
    if not isinstance(field_value, dict) or not field_value.get("value"):
        return False
    normalized = _iso_birth_date(field_value.get("value"))
    if normalized is None:
        return False
    field_value["value"] = normalized
    return True


def _validate_passport_identity_authority(
    case_data: dict,
    raw_candidates: list,
    documents: list[dict],
    review: dict,
) -> None:
    """Fail closed unless passport identity-page evidence is unambiguous.

    Only name and birth date are gated here because those are the fields whose
    exact passport transcription is required.  Candidate metadata never enters
    canonical case_data.  We do not add an OCR dependency: the deterministic
    checks use the manifest and the existing source_ref contract only.
    """
    review.setdefault("validation_errors", [])
    review.setdefault("findings", [])
    review.setdefault("missing_items", [])

    candidates, invalid_count = _normalize_passport_identity_candidates(
        raw_candidates,
        documents,
    )
    applicant = case_data.get("applicant") if isinstance(case_data, dict) else None
    applicant_present = isinstance(applicant, dict)
    if not applicant_present:
        applicant = {}
    withheld_labels: list[str] = []
    invalid_birth_date = False
    birth_date_field = applicant.get("birth_date")
    if isinstance(birth_date_field, dict) and birth_date_field.get("value"):
        if not _normalize_passport_birth_date_field(birth_date_field):
            invalid_birth_date = True
            if _withhold_field_value(birth_date_field):
                withheld_labels.append("生年月日")
            review["validation_errors"].append(
                "生年月日を曖昧さなくYYYY-MM-DDへ正規化できないため、自動確定できません。"
            )
    block_reason: str | None = None
    candidate: dict | None = None
    if not applicant_present:
        block_reason = "申請人の本人情報を抽出できないため、旅券記載との一致を確認できません。"
    elif invalid_count:
        block_reason = (
            "旅券身分事項ページ候補に、対象外の書類形式、書類一覧と一致しないdocument_id、"
            "または実ページ範囲外のページ番号が含まれるため、自動確定できません。"
        )
    elif not candidates:
        block_reason = "旅券身分事項ページを一意に確認できません（候補なし）。"
    elif len(candidates) > 1:
        block_reason = "旅券身分事項ページを一意に確認できません（候補が複数あります）。"
    else:
        candidate = candidates[0]
        if candidate["confidence"] < PASSPORT_IDENTITY_MIN_CONFIDENCE:
            block_reason = "旅券身分事項ページ候補の確信度が低いため、自動確定できません。"

    verified_fields: list[str] = []
    blocked_fields: list[str] = []
    if block_reason:
        for field_name, (field_path, label) in PASSPORT_IDENTITY_FIELDS.items():
            if _withhold_field_value(applicant.get(field_name)):
                withheld_labels.append(label)
            blocked_fields.append(field_path)
        review["validation_errors"].append(block_reason)
    elif candidate is not None:
        for field_name, (field_path, label) in PASSPORT_IDENTITY_FIELDS.items():
            field_value = applicant.get(field_name)
            if field_name == "birth_date" and invalid_birth_date:
                blocked_fields.append(field_path)
            elif not _source_matches_passport_page(field_value, candidate):
                if _withhold_field_value(field_value):
                    withheld_labels.append(label)
                blocked_fields.append(field_path)
                review["validation_errors"].append(
                    f"{label}の出典が、一意に検出した旅券身分事項ページと一致しません。"
                )
            elif _source_looks_like_mrz(field_value):
                if _withhold_field_value(field_value):
                    withheld_labels.append(label)
                blocked_fields.append(field_path)
                review["validation_errors"].append(
                    f"{label}の出典引用がMRZ形式のため、顔写真側の身分事項欄(VIZ)を確認してください。"
                )
            else:
                verified_fields.append(field_path)

    status = "verified" if not blocked_fields else "blocked"
    if status == "blocked":
        review["expected_route"] = "needs_review"
    review["passport_identity_authority"] = {
        "status": status,
        "required_action": "none" if status == "verified" else "human_required",
        "candidates": [
            {"document_id": item["document_id"], "page": item["page"]}
            for item in candidates
        ],
        "verified_fields": verified_fields,
        "blocked_fields": blocked_fields,
    }

    if withheld_labels:
        labels = "・".join(withheld_labels)
        review["findings"].append(
            f"{labels}は旅券出典を機械的に確認できないため自動確定せず、抽出値を別候補として保持しました。"
        )
        review["missing_items"].append(
            f"旅券身分事項ページを確認し、{labels}を確定してください。"
        )


def _normalized_text_key(value) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[\s/_・（）()]+", "", text)


def _field_value_value(field_value) -> object:
    return field_value.get("value") if isinstance(field_value, dict) else None


def _field_value_has_non_empty_value(field_value) -> bool:
    value = _field_value_value(field_value)
    return value is not None and str(value).strip() != ""


def _field_value_has_source_refs(field_value) -> bool:
    if not isinstance(field_value, dict):
        return False
    source_refs = field_value.get("source_refs")
    return isinstance(source_refs, list) and bool(source_refs)


def _set_derived_field_value(field_value: dict, value) -> None:
    field_value["value"] = value
    field_value["origin"] = "derived"
    field_value["source_refs"] = []
    field_value.pop("alternatives", None)


def _review_list(review: dict, key: str) -> list:
    current = review.get(key)
    if isinstance(current, list):
        return current
    current = []
    review[key] = current
    return current


def _add_review_issue(review: dict, message: str, *, missing_item: str | None = None) -> None:
    _review_list(review, "validation_errors").append(message)
    if missing_item:
        _review_list(review, "missing_items").append(missing_item)
    review["expected_route"] = "needs_review"


def _normalize_internal_enum_field(case_data: dict, path: tuple[str, ...], aliases: dict[str, str]) -> None:
    current = case_data
    for key in path[:-1]:
        current = current.get(key) if isinstance(current, dict) else None
        if not isinstance(current, dict):
            return
    field_value = current.get(path[-1])
    if not isinstance(field_value, dict):
        return
    value = field_value.get("value")
    key = _normalized_text_key(value)
    normalized = aliases.get(key)
    if normalized:
        field_value["value"] = normalized


def _normalize_internal_enums(case_data: dict) -> None:
    _normalize_internal_enum_field(
        case_data,
        ("applicant", "sex"),
        _SEX_INTERNAL_VALUES,
    )
    _normalize_internal_enum_field(
        case_data,
        ("applicant", "marital_status"),
        _MARITAL_STATUS_INTERNAL_VALUES,
    )


def _normalize_corporate_number(case_data: dict, review: dict) -> None:
    """Accept only 13-digit corporate numbers after removing symbols."""
    employer = case_data.get("employer", {})
    if not isinstance(employer, dict):
        return
    cn = employer.get("corporate_number")
    has_corporate_number = employer.get("has_corporate_number")
    if not isinstance(cn, dict):
        return

    raw_value = cn.get("value")
    if raw_value is None or str(raw_value).strip() == "":
        if isinstance(has_corporate_number, dict):
            _set_derived_field_value(has_corporate_number, False)
        return
    digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", str(raw_value)))
    if len(digits) == 13:
        cn["value"] = digits
        if isinstance(has_corporate_number, dict):
            _set_derived_field_value(has_corporate_number, True)
        return

    _set_derived_field_value(cn, "")
    if isinstance(has_corporate_number, dict):
        _set_derived_field_value(has_corporate_number, False)
    _add_review_issue(
        review,
        "法人番号は記号除去後に13桁でないため、自動確定できません。12桁値は補完せず空欄にしました。",
        missing_item="13桁の法人番号を確認してください。",
    )


def _normalize_full_iso_date(value) -> str | None:
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw:
        return None
    match = re.fullmatch(
        r"(\d{4})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:[-/.]|月)\s*(\d{1,2})\s*(?:日)?",
        raw,
    )
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize_joining_date(case_data: dict, review: dict) -> None:
    employment = case_data.get("employment", {})
    if not isinstance(employment, dict):
        return
    joining_date = employment.get("joining_date")
    if not isinstance(joining_date, dict) or not _field_value_has_non_empty_value(joining_date):
        return

    normalized = _normalize_full_iso_date(joining_date.get("value"))
    if normalized:
        joining_date["value"] = normalized
        return

    _set_derived_field_value(joining_date, "")
    _add_review_issue(
        review,
        "入社日はYYYY-MM-DDの完全な日付として確認できないため、自動で日付補完せず空欄にしました。",
        missing_item="入社日の年月日を確認してください。",
    )


def _align_has_position(case_data: dict, review: dict) -> None:
    employment = case_data.get("employment", {})
    if not isinstance(employment, dict):
        return
    has_position = employment.get("has_position")
    position_title = employment.get("position_title")
    if not isinstance(has_position, dict):
        return
    title_present = _field_value_has_non_empty_value(position_title)
    has_refs = _field_value_has_source_refs(has_position)
    title_has_refs = _field_value_has_source_refs(position_title)

    if has_position.get("value") is False and title_present:
        if has_refs and title_has_refs:
            _add_review_issue(
                review,
                "役職なしの根拠と役職名の根拠が矛盾しているため、自動確定できません。",
                missing_item="役職の有無と役職名を確認してください。",
            )
    elif has_position.get("value") is True and not title_present:
        if has_refs:
            _add_review_issue(
                review,
                "役職ありの根拠がありますが役職名を確認できないため、自動確定できません。",
                missing_item="役職名を確認してください。",
            )

    _set_derived_field_value(has_position, title_present)


def _apply_targeted_case_data_normalizations(case_data: dict, review: dict) -> None:
    _normalize_internal_enums(case_data)
    _normalize_corporate_number(case_data, review)
    _normalize_joining_date(case_data, review)
    _align_has_position(case_data, review)


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


def _normalize_source_ref(source_ref) -> dict | None:
    """Normalize a single source_ref dict into field_metadata source_refs item."""
    if not isinstance(source_ref, dict):
        return None
    document_id = str(source_ref.get("document_id") or "").strip()
    text_quote = str(source_ref.get("text_quote") or "").strip()
    if not document_id or not text_quote:
        return None
    try:
        page = int(source_ref.get("page", 1))
    except (ValueError, TypeError):
        page = 1
    try:
        confidence = float(source_ref.get("confidence", 0))
    except (ValueError, TypeError):
        confidence = 0.0
    ref = {
        "document_id": document_id,
        "page": page,
        "text_quote": text_quote,
        "confidence": confidence,
    }
    locations = _normalize_source_locations(source_ref.get("locations"))
    if locations:
        ref["locations"] = locations
    elif isinstance(source_ref.get("locations"), list):
        ref["locations"] = []
    return ref


def _normalize_source_locations(locations) -> list[dict]:
    if not isinstance(locations, list):
        return []

    normalized = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        location_type = str(location.get("type") or "").strip()
        if not location_type:
            continue
        normalized_location = {"type": location_type}
        anchor_id = str(location.get("anchor_id") or "").strip()
        if anchor_id:
            normalized_location["anchor_id"] = anchor_id
        try:
            page = int(location.get("page"))
        except (TypeError, ValueError):
            page = None
        if page is not None:
            normalized_location["page"] = page
        bbox = location.get("bbox")
        if isinstance(bbox, dict):
            normalized_bbox = {}
            for key in ("y_min", "x_min", "y_max", "x_max"):
                try:
                    normalized_bbox[key] = float(bbox[key])
                except (KeyError, TypeError, ValueError):
                    normalized_bbox = {}
                    break
            if normalized_bbox:
                normalized_location["bbox"] = normalized_bbox
        normalized.append(normalized_location)
    return normalized


def _normalize_alternative_value(value) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def _log_alternative_filter_counts(counts: dict[str, int]) -> None:
    if not any(counts.values()):
        return
    logger.info(
        "gemini_metric event=alternatives_filtered same_value=%d empty_value=%d empty_quote=%d truncated=%d",
        counts["same_value"],
        counts["empty_value"],
        counts["empty_quote"],
        counts["truncated"],
    )


def _normalize_alternatives(primary_value, alternatives, counts: dict[str, int]) -> list[dict]:
    if not isinstance(alternatives, list):
        return []

    normalized_primary = _normalize_alternative_value(primary_value)
    normalized_alternatives = []
    seen_values: set[str] = set()

    for alternative in alternatives:
        if not isinstance(alternative, dict):
            continue
        value = alternative.get("value")
        normalized_value = _normalize_alternative_value(value)
        if not normalized_value:
            counts["empty_value"] += 1
            continue
        if normalized_value == normalized_primary or normalized_value in seen_values:
            counts["same_value"] += 1
            continue
        ref = _normalize_source_ref(alternative.get("source_ref"))
        if not ref:
            source_ref = alternative.get("source_ref")
            if not isinstance(source_ref, dict) or not str(source_ref.get("text_quote") or "").strip():
                counts["empty_quote"] += 1
            continue
        normalized_alternative = {
            "value": value,
            "origin": _normalized_origin(ref),
            "source_refs": [ref],
        }
        normalized_alternatives.append(normalized_alternative)
        seen_values.add(normalized_value)

    if len(normalized_alternatives) > 2:
        counts["truncated"] += len(normalized_alternatives) - 2
        normalized_alternatives = normalized_alternatives[:2]
    return normalized_alternatives


def _normalized_origin(source_ref: dict | None) -> str:
    return "document" if source_ref else "derived"


def _field_value_at_path(case_data: dict, field_path: str) -> dict | None:
    current = case_data
    for part in field_path.split("."):
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current if isinstance(current, dict) else None


def _initialize_source_locations(obj) -> None:
    if isinstance(obj, dict):
        if "value" in obj and isinstance(obj.get("source_ref"), dict):
            obj["source_ref"].setdefault("locations", [])
            for alternative in obj.get("alternatives") or []:
                if isinstance(alternative, dict) and isinstance(alternative.get("source_ref"), dict):
                    alternative["source_ref"].setdefault("locations", [])
            return
        for value in obj.values():
            _initialize_source_locations(value)
    elif isinstance(obj, list):
        for item in obj:
            _initialize_source_locations(item)


def _attach_source_locations(case_data: dict, source_locations) -> None:
    """Attach the scope-level location list to its FieldValue source_refs."""
    _initialize_source_locations(case_data)
    attached = 0
    ignored = 0
    for item in source_locations if isinstance(source_locations, list) else []:
        if not isinstance(item, dict):
            ignored += 1
            continue
        field_value = _field_value_at_path(case_data, str(item.get("field_path") or ""))
        alternative_index = item.get("alternative_index")
        if field_value is None or not isinstance(alternative_index, int):
            ignored += 1
            continue
        if alternative_index == -1:
            source_ref = field_value.get("source_ref")
        else:
            alternatives = field_value.get("alternatives") or []
            source_ref = (
                alternatives[alternative_index].get("source_ref")
                if 0 <= alternative_index < len(alternatives)
                and isinstance(alternatives[alternative_index], dict)
                else None
            )
        if not isinstance(source_ref, dict):
            ignored += 1
            continue
        location = {
            key: value
            for key, value in item.items()
            if key not in {"field_path", "alternative_index"}
        }
        source_ref["locations"].append(location)
        attached += 1
    logger.info(
        "gemini_metric event=source_locations_attached attached=%d ignored=%d",
        attached,
        ignored,
    )


def _unflatten_field_values(obj, alternative_counts: dict[str, int] | None = None):
    """Convert Gemini FieldValue into standard
    {value, source_refs: [{document_id, page, text_quote, confidence}]} format.
    """
    if alternative_counts is None:
        alternative_counts = {
            "same_value": 0,
            "empty_value": 0,
            "empty_quote": 0,
            "truncated": 0,
        }
    if isinstance(obj, dict):
        if "value" in obj and "source_ref" in obj and "source_refs" not in obj:
            ref = _normalize_source_ref(obj.get("source_ref"))
            source_refs = [ref] if ref else []
            result = {
                "value": obj.get("value"),
                "origin": _normalized_origin(ref),
                "source_refs": source_refs,
            }
            alternatives = _normalize_alternatives(
                obj.get("value"),
                obj.get("alternatives"),
                alternative_counts,
            )
            if alternatives:
                result["alternatives"] = alternatives
            return result
        return {k: _unflatten_field_values(v, alternative_counts) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_unflatten_field_values(item, alternative_counts) for item in obj]
    return obj


def _uses_raw_source_refs(obj) -> bool:
    """Detect old Gemini raw FieldValue format using source_refs directly."""
    if isinstance(obj, dict):
        if "value" in obj and "source_refs" in obj and "source_ref" not in obj:
            return True
        return any(_uses_raw_source_refs(value) for value in obj.values())
    if isinstance(obj, list):
        return any(_uses_raw_source_refs(item) for item in obj)
    return False


def _build_extraction_result(parsed: dict) -> ExtractionResult:
    """Gemini のパース結果から ExtractionResult を構築する。

    Gemini response_schema の FieldValue 構造を、UI/API用の value-only
    case_data と field_metadata.source_refs[] に分ける。
    """
    raw_case_data = parsed.get("case_data", {})
    _attach_source_locations(raw_case_data, parsed.pop("source_locations", []))
    if _uses_raw_source_refs(raw_case_data):
        raise ValueError("Gemini response must use source_ref, not source_refs")
    alternative_filter_counts = {
        "same_value": 0,
        "empty_value": 0,
        "empty_quote": 0,
        "truncated": 0,
    }
    raw_case_data = _unflatten_field_values(raw_case_data, alternative_filter_counts)
    _log_alternative_filter_counts(alternative_filter_counts)
    parsed["case_data"] = raw_case_data
    review = parsed.get("review")
    if not isinstance(review, dict):
        review = {}
        parsed["review"] = review

    _apply_targeted_case_data_normalizations(raw_case_data, review)

    if not _is_new_format(raw_case_data):
        raise ValueError("Gemini response case_data must use FieldValue objects with source_ref")

    field_metadata = _extract_field_metadata(raw_case_data)
    display_case_data = _extract_display_values(raw_case_data)
    _normalize_source_refs_in_metadata(field_metadata)
    _log_source_coverage(field_metadata, display_case_data)
    return ExtractionResult(
        case_data=raw_case_data,
        display_case_data=display_case_data,
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
    def normalize_refs(refs: list) -> None:
        if not isinstance(refs, list):
            return
        for ref in refs:
            if not isinstance(ref, dict):
                continue
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
            if "confidence" in ref and isinstance(ref["confidence"], str):
                try:
                    ref["confidence"] = float(ref["confidence"])
                except (ValueError, TypeError):
                    ref["confidence"] = 0.0

    normalize_refs(meta.get("source_refs", []))
    for alternative in meta.get("alternatives", []):
        if isinstance(alternative, dict):
            normalize_refs(alternative.get("source_refs", []))


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
    # Scoped responses attach before section merge. The build-stage call is
    # the equivalent path for the legacy non-scoped response.
    case_data = raw.get("case_data", raw)
    _attach_source_locations(case_data, raw.pop("source_locations", []))
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

    Extraction scopes run in parallel. Then review runs sequentially with
    merged value-only data as context.
    Then review (S6) — sequential, using merged results as context.
    """
    extraction_scopes = EXTRACTION_SCOPES

    def all_failed_message(failures: dict[str, str]) -> str:
        first_error = next(iter(failures.values()), "")
        if "status=401" in first_error or "status=403" in first_error:
            return "Gemini API key is invalid or not permitted. Check GOOGLE_API_KEY."
        if "status=429" in first_error:
            return "Gemini API quota was exhausted."
        return f"All extraction scopes failed: {', '.join(failures)}"

    def contents_for(scope: str) -> list:
        if isinstance(contents, dict):
            return contents.get(scope) or contents.get("default") or []
        return contents

    def documents_for(scope: str) -> list[dict]:
        if isinstance(documents, dict):
            return documents.get(scope) or documents.get("default") or []
        return documents

    # Phase 1: extraction scopes in parallel via ThreadPoolExecutor.
    # Keep worker count modest; each scope still receives all documents until routing exists.
    max_workers = min(4, len(extraction_scopes))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
                logger.warning(
                    "Scope %s failed: %s",
                    scope,
                    _safe_gemini_error_label(e),
                )
                scope_results[scope] = {}
                failed_scopes[scope] = _safe_gemini_error_label(e)

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
            raise RuntimeError(all_failed_message(failed_scopes))
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
    passport_identity_candidates = _pop_passport_identity_candidates(
        scope_results.get("applicant_identity", {})
    )
    merged_case_data: dict = {}
    for scope, result in scope_results.items():
        # Each scope returns a flat dict of sections (e.g. {"applicant": {...}, "passport": {...}})
        # or may be wrapped in "case_data" key — handle both
        data = result.get("case_data", result) if isinstance(result, dict) else {}
        _deep_merge_case_data(merged_case_data, data)

    # Phase 3: Review (S6) — sequential, with value-only merged data as context
    review: dict = {}
    try:
        review_schema_key = _SCOPE_KEY_MAP["review"]
        review_schema = SCOPE_SCHEMAS.get(review_schema_key)
        review_context = _extract_display_values(
            _unflatten_field_values(copy.deepcopy(merged_case_data))
        )
        review_prompt = build_scoped_prompt(
            "review", case_meta, documents_for("review"), extra_context=review_context,
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
        logger.warning("Review scope failed: %s", _safe_gemini_error_label(e))
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

    # The LLM review is advisory.  Passport authority is enforced
    # deterministically after review so its result cannot be overwritten by a
    # model response and helper metadata cannot leak into canonical case_data.
    _validate_passport_identity_authority(
        merged_case_data,
        passport_identity_candidates,
        documents_for("applicant_identity"),
        review,
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
