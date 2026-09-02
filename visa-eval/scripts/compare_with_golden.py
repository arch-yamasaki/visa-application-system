#!/usr/bin/env python3
"""Compare generated output with golden (expected) files.

Usage:
    python visa-eval/scripts/compare_with_golden.py \
        --generated <generated_dir> \
        --expected <expected_dir> \
        [--targets case_data] [--output <file>] [--json]

If --output is omitted, the report is saved to <generated_dir>/comparison_report.md
and a summary is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_application_data import build_rows  # noqa: E402

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_EMPTY_SYNONYMS = {None, "", "unknown", "n/a", "na", "null"}
_SKIP_KEYS_CASE_DATA = {"source_refs", "field_metadata", "schema_version", "case"}
_MANIFEST_NAME = "golden_manifest.json"
_SCORED_SCOPE = "extraction"
_SCORED_VERIFICATION = "verified"


def _normalise(value: Any, path: str = "") -> Any:
    return _normalise_for_path(value, path)


def _values_match(generated: Any, expected: Any, path: str) -> bool:
    if _requires_full_date(path):
        generated_date = _normalise_full_date(generated)
        expected_date = _normalise_full_date(expected)
        return generated_date is not None and generated_date == expected_date
    if _is_country_path(path):
        generated_keys = _country_keys(generated)
        expected_keys = _country_keys(expected)
        if generated_keys and expected_keys:
            return bool(generated_keys & expected_keys)
    return _normalise(generated, path) == _normalise(expected, path)


def _normalise_for_path(value: Any, path: str) -> Any:
    path = path.lower()
    if _is_empty(value):
        return None
    if _is_boolean_path(path):
        return _normalise_boolean(value)
    if path.endswith("marital_status"):
        return _normalise_marital_status(value)
    if path.endswith("sex"):
        return _normalise_sex(value)
    if _is_country_path(path):
        return _normalise_country(value)
    if _is_relationship_path(path):
        return _normalise_relationship(value)
    if _is_label_path(path):
        return _normalise_label(value)
    if _is_date_path(path):
        return _normalise_date(value)
    if _is_number_path(path):
        return _normalise_digits(value)
    return _normalise_string(value)


def _is_empty(value: Any) -> bool:
    if isinstance(value, str):
        v = _normalise_text(value)
        return v in _EMPTY_SYNONYMS
    return value is None


def _normalise_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalise_string(value: Any) -> Any:
    if isinstance(value, str):
        return _normalise_text(value)
    return value


def _is_boolean_path(path: str) -> bool:
    leaf = path.rsplit(".", 1)[-1]
    return leaf.startswith("has_") or leaf in {
        "criminal_record",
        "deportation_or_departure_order",
        "end_month_unknown",
        "start_month_unknown",
    }


def _normalise_boolean(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = _normalise_text(value)
        if v in {"true", "yes", "y", "有", "あり", "有 yes", "1"}:
            return True
        if v in {"false", "no", "n", "無", "なし", "無し", "ない", "無 no", "0"}:
            return False
    return _normalise_string(value)


def _normalise_marital_status(value: Any) -> Any:
    if isinstance(value, str):
        v = _normalise_text(value)
        if v in {"single", "unmarried", "無", "なし", "無し", "無 single"}:
            return "single"
        if v in {"married", "有", "あり", "有 married"}:
            return "married"
    return _normalise_string(value)


def _normalise_sex(value: Any) -> Any:
    if isinstance(value, str):
        v = _normalise_text(value)
        if v in {"male", "m", "男", "男 male"}:
            return "male"
        if v in {"female", "f", "女", "女 female"}:
            return "female"
    return _normalise_string(value)


def _is_country_path(path: str) -> bool:
    return path.endswith("nationality_region") or path.endswith("country_region") or path.endswith("country_type")


def _normalise_country(value: Any) -> Any:
    keys = _country_keys(value)
    if keys:
        return " ".join(sorted(keys))
    return _normalise_string(value)


def _country_keys(value: Any) -> set[str]:
    if not isinstance(value, str):
        normalized = _normalise_string(value)
        return {str(normalized)} if normalized is not None else set()

    v = _normalise_text(value).replace("viet nam", "vietnam")
    v = re.sub(r"\s+", " ", v)
    japanese_aliases = {
        "外国": "foreign",
        "本邦": "japan",
        "日本": "japan",
        "ネパール": "nepal",
        "中国": "china",
        "ベトナム": "vietnam",
        "フィリピン": "philippines",
        "インドネシア": "indonesia",
        "ミャンマー": "myanmar",
        "韓国": "korea",
        "パキスタン": "pakistan",
        "バングラデシュ": "bangladesh",
    }
    keys = {alias for label, alias in japanese_aliases.items() if _contains_label_token(v, label)}

    nationality_aliases = {
        "bgd": "bangladesh",
        "chn": "china",
        "idn": "indonesia",
        "ind": "india",
        "jpn": "japan",
        "kor": "korea",
        "mmr": "myanmar",
        "nep": "nepal",
        "npl": "nepal",
        "pak": "pakistan",
        "phl": "philippines",
        "tha": "thailand",
        "vnm": "vietnam",
        "nepali": "nepal",
        "japanese": "japan",
        "chinese": "china",
        "indian": "india",
        "vietnamese": "vietnam",
        "indonesian": "indonesia",
        "filipino": "philippines",
        "korean": "korea",
        "thai": "thailand",
        "pakistani": "pakistan",
        "bangladeshi": "bangladesh",
    }
    country_tokens = {
        "bangladesh",
        "china",
        "foreign",
        "india",
        "indonesia",
        "japan",
        "korea",
        "myanmar",
        "nepal",
        "pakistan",
        "philippines",
        "thailand",
        "vietnam",
    }
    stopwords = {
        "country",
        "nationality",
        "of",
        "region",
        "the",
        "republic",
        "people",
        "s",
        "state",
        "states",
        "kingdom",
        "united",
    }
    unknown_tokens: list[str] = []
    for token in re.findall(r"[a-z]+", v):
        token = nationality_aliases.get(token, token)
        if token in stopwords:
            continue
        if token in country_tokens:
            keys.add(token)
        else:
            unknown_tokens.append(token)
    if keys and unknown_tokens:
        return set()
    return keys


def _contains_label_token(value: str, label: str) -> bool:
    return (
        value == label
        or value.startswith(f"{label} ")
        or value.endswith(f" {label}")
        or f" {label} " in value
    )


def _is_relationship_path(path: str) -> bool:
    return path.endswith("relationship")


def _normalise_relationship(value: Any) -> Any:
    if not isinstance(value, str):
        return _normalise_string(value)

    v = _normalise_text(value)
    aliases = {
        "wife": "wife",
        "妻": "wife",
        "妻 wife": "wife",
        "wife 妻": "wife",
        "husband": "husband",
        "夫": "husband",
        "夫 husband": "husband",
        "husband 夫": "husband",
        "father": "father",
        "父": "father",
        "父 father": "father",
        "father 父": "father",
        "mother": "mother",
        "母": "mother",
        "母 mother": "mother",
        "mother 母": "mother",
        "child": "child",
        "子": "child",
        "子 child": "child",
        "child 子": "child",
        "spouse": "spouse",
        "配偶者": "spouse",
        "配偶者 spouse": "spouse",
        "spouse 配偶者": "spouse",
    }
    return aliases.get(v, _normalise_label(value))


def _is_label_path(path: str) -> bool:
    return path.endswith((
        "contract_type",
        "employment_period_type",
        "industry_primary",
        "job_category_primary",
        "level",
        "major_field",
        "purpose_of_entry",
        "planned_port",
    ))


def _normalise_label(value: Any) -> Any:
    if not isinstance(value, str):
        return _normalise_string(value)

    v = unicodedata.normalize("NFKC", value)
    v = re.sub(r"\s+", " ", v).strip()
    aliases = {
        "有期": "定めあり",
        "定めあり Fixed": "定めあり",
        "雇用 Employment": "雇用",
        "Employment": "雇用",
        "その他 Others": "その他",
        "Others": "その他",
    }
    if v in aliases:
        return aliases[v]

    if re.search(r"[ぁ-んァ-ン一-龥]", v):
        return v.split(" ", 1)[0].casefold()
    return v.casefold()


def _is_date_path(path: str) -> bool:
    return path.endswith("date") or path.endswith("graduation_date") or path.endswith("expiry_date")


def _requires_full_date(path: str) -> bool:
    return path.lower().endswith("joining_date")


def _normalise_full_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKC", value).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if re.fullmatch(r"\d{8}", digits) and re.fullmatch(r"\d{8}", text):
        parts = (int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    else:
        match = re.fullmatch(
            r"(\d{4})\s*(?:[-/.]|年)\s*(\d{1,2})\s*(?:[-/.]|月)\s*(\d{1,2})\s*(?:日)?",
            text,
        )
        if not match:
            return None
        parts = tuple(int(part) for part in match.groups())
    try:
        return date(*parts).isoformat()
    except ValueError:
        return None


def _normalise_date(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", value))
    if len(digits) == 8:
        return digits
    if len(digits) == 6:
        return digits
    return _normalise_string(value)


def _is_number_path(path: str) -> bool:
    leaf = path.rsplit(".", 1)[-1]
    return leaf.endswith((
        "count",
        "jpy",
        "salary",
        "phone",
        "number",
        "years",
        "months",
    ))


def _normalise_digits(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", value))
        return digits if digits else _normalise_string(value)
    return value


def _display(value: Any, max_len: int = 60) -> str:
    """Format a value for table display."""
    if value is None:
        return ""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s


def _canonical_compare_path(path: str) -> str:
    """Normalize manifest dot-index paths to the compare report's bracket style."""
    return re.sub(r"\.(\d+)(?=\.|$)", r"[\1]", path)


# ---------------------------------------------------------------------------
# Flatten nested JSON to dot-path dict
# ---------------------------------------------------------------------------


def _flatten(obj: Any, prefix: str = "", skip_keys: set[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if skip_keys is None:
        skip_keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip_keys:
                continue
            key = f"{prefix}.{k}" if prefix else k
            out.update(_flatten(v, key, skip_keys))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            key = f"{prefix}[{i}]"
            out.update(_flatten(v, key, skip_keys))
    else:
        out[prefix] = obj
    return out


def _split_path(dot_path: str) -> tuple[str, str]:
    """Split a dot path into (大項目, 小項目)."""
    # e.g. "applicant.name_roman" -> ("applicant", "name_roman")
    # e.g. "education[0].school_name" -> ("education", "[0].school_name")
    # e.g. "case.case_id" -> ("case", "case_id")
    parts = dot_path.split(".", 1)
    if len(parts) == 1:
        # check for array index at top level
        if "[" in parts[0]:
            base = parts[0].split("[", 1)
            return base[0], "[" + base[1]
        return parts[0], ""
    major = parts[0]
    minor = parts[1]
    # If major contains array index, split it
    if "[" in major:
        base = major.split("[", 1)
        return base[0], "[" + base[1] + "." + minor
    return major, minor


# ---------------------------------------------------------------------------
# Unified comparison row
# ---------------------------------------------------------------------------

ROW_MATCH = "✅ 一致"
ROW_MISMATCH = "❌ 不一致"
ROW_MISSING = "⚠️ 抽出漏れ"
ROW_EXTRA = "➕ 過剰抽出"


def _build_golden_rows(gen_flat: dict, exp_flat: dict) -> list[dict]:
    """Build comparison rows for all golden-expected fields."""
    rows: list[dict] = []

    # Golden fields (expected): match, mismatch, missing
    for key in sorted(exp_flat.keys()):
        ev = exp_flat[key]
        ev_norm = _normalise(ev, key)
        major, minor = _split_path(key)

        if key in gen_flat:
            gv = gen_flat[key]
            if _values_match(gv, ev, key):
                status = ROW_MATCH
            else:
                status = ROW_MISMATCH
        else:
            gv = None
            if ev_norm is None:
                status = ROW_MATCH  # both empty
            else:
                status = ROW_MISSING

        rows.append({
            "path": key,
            "major": major,
            "minor": minor,
            "expected": ev,
            "generated": gv,
            "status": status,
        })

    return rows


# ---------------------------------------------------------------------------
# case_data comparison
# ---------------------------------------------------------------------------


def _load_golden_manifest(expected_dir: Path) -> dict | None:
    manifest_path = expected_dir / _MANIFEST_NAME
    if not manifest_path.exists():
        return None
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        print(f"ERROR: {_MANIFEST_NAME} must be a JSON object", file=sys.stderr)
        sys.exit(1)
    return manifest


def _case_data_manifest_stats(exp_flat: dict[str, Any], manifest: dict | None) -> dict[str, Any]:
    if manifest is None:
        return {
            "comparison_mode": "legacy_all_fields",
            "golden_manifest_present": False,
            "manifest_status": None,
            "manifest_revision_id": None,
            "application_only_count": 0,
            "excluded_count": 0,
            "needs_review_count": 0,
            "unclassified_count": 0,
            "manifest_unknown_path_count": 0,
            "manifest_unknown_paths": [],
        }

    field_rules = manifest.get("field_rules", {})
    if not isinstance(field_rules, dict):
        print(f"ERROR: {_MANIFEST_NAME}.field_rules must be a JSON object", file=sys.stderr)
        sys.exit(1)

    expected_paths = set(exp_flat.keys())
    expected_compare_paths = {_canonical_compare_path(path) for path in expected_paths}
    field_rules_by_path = {_canonical_compare_path(path): rule for path, rule in field_rules.items()}
    scored_paths: set[str] = set()
    application_only = 0
    excluded = 0
    needs_review = 0
    unclassified = 0

    for path in expected_paths:
        rule = field_rules_by_path.get(_canonical_compare_path(path))
        if not isinstance(rule, dict):
            unclassified += 1
            continue

        scope = rule.get("scope")
        verification = rule.get("verification")
        if scope == _SCORED_SCOPE and verification == _SCORED_VERIFICATION:
            scored_paths.add(path)
        elif scope == _SCORED_SCOPE:
            needs_review += 1
        elif scope == "application_only":
            application_only += 1
            if verification != _SCORED_VERIFICATION:
                needs_review += 1
        elif scope == "excluded":
            excluded += 1
            if verification != _SCORED_VERIFICATION:
                needs_review += 1
        else:
            unclassified += 1

    unknown_paths = sorted(
        path for path in field_rules.keys()
        if _canonical_compare_path(path) not in expected_compare_paths
    )
    return {
        "comparison_mode": "manifest_scoped",
        "golden_manifest_present": True,
        "manifest_status": manifest.get("status"),
        "manifest_revision_id": manifest.get("revision_id"),
        "scored_paths": scored_paths,
        "application_only_count": application_only,
        "excluded_count": excluded,
        "needs_review_count": needs_review,
        "unclassified_count": unclassified,
        "manifest_unknown_path_count": len(unknown_paths),
        "manifest_unknown_paths": unknown_paths,
    }


def compare_case_data(gen: dict, exp: dict, manifest: dict | None = None) -> dict:
    gen_flat = _flatten(gen, skip_keys=_SKIP_KEYS_CASE_DATA)
    exp_flat = _flatten(exp, skip_keys=_SKIP_KEYS_CASE_DATA)

    manifest_stats = _case_data_manifest_stats(exp_flat, manifest)
    if manifest is None:
        scored_exp_flat = exp_flat
    else:
        scored_exp_flat = {path: exp_flat[path] for path in manifest_stats["scored_paths"]}

    rows = _build_golden_rows(gen_flat, scored_exp_flat)
    match = sum(1 for r in rows if r["status"] == ROW_MATCH)
    mismatch = sum(1 for r in rows if r["status"] == ROW_MISMATCH)
    missing = sum(1 for r in rows if r["status"] == ROW_MISSING)

    # Extra values do not change the golden-based accuracy denominator, but
    # must stay visible in both modes. They can be an AI hallucination or a
    # missing field in the golden and therefore always need review.
    extra_keys = sorted(set(gen_flat.keys()) - set(exp_flat.keys()))
    extra = [k for k in extra_keys if _normalise(gen_flat[k], k) is not None]

    golden_total = match + mismatch + missing
    config_errors: list[str] = []
    if manifest is not None and not golden_total:
        config_errors.append("golden_manifest has no verified extraction fields")
    if manifest_stats["manifest_unknown_path_count"]:
        config_errors.append("golden_manifest contains path(s) not present in case_data.golden.json")

    if config_errors:
        status = "CONFIG_ERROR"
    elif not mismatch and not missing and not extra:
        status = "MATCH"
    else:
        status = "MISMATCH"

    return {
        "file": "case_data",
        "status": status,
        "golden_total": golden_total,
        "match_count": match,
        "mismatch_count": mismatch,
        "only_expected_count": missing,
        "only_generated_count": len(extra),
        "rows": rows,
        "only_generated": extra,
        "config_errors": config_errors,
        **{k: v for k, v in manifest_stats.items() if k != "scored_paths"},
    }


# ---------------------------------------------------------------------------
# review comparison
# ---------------------------------------------------------------------------

_REVIEW_EXACT_KEYS = {"case_id", "expected_route"}
_REVIEW_SET_FIELDS = {"missing_documents", "missing_items", "validation_errors", "findings", "assessments"}
_REVIEW_SKIP_KEYS = {"schema_version", "golden_status", "expected_workflow_state"}


def _set_key(item: Any) -> str:
    if isinstance(item, dict):
        for k in ("path", "code", "type"):
            if k in item:
                return f"{k}={item[k]}"
        return json.dumps(item, sort_keys=True, ensure_ascii=False)
    return str(item)


def compare_review(gen: dict, exp: dict) -> dict:
    rows: list[dict] = []
    only_generated: list[str] = []

    for k in sorted(_REVIEW_EXACT_KEYS):
        gv = gen.get(k)
        ev = exp.get(k)
        status = ROW_MATCH if _normalise(gv, k) == _normalise(ev, k) else ROW_MISMATCH
        rows.append({"path": k, "major": "review", "minor": k,
                      "expected": ev, "generated": gv, "status": status})

    for field in sorted(_REVIEW_SET_FIELDS):
        gen_list = gen.get(field, []) or []
        exp_list = exp.get(field, []) or []
        gen_by_key = {_set_key(it): it for it in gen_list}
        exp_by_key = {_set_key(it): it for it in exp_list}

        for key in sorted(exp_by_key.keys()):
            path = f"{field}[{key}]"
            ev = exp_by_key[key]
            if key in gen_by_key:
                gv = gen_by_key[key]
                if json.dumps(gv, sort_keys=True) == json.dumps(ev, sort_keys=True):
                    status = ROW_MATCH
                else:
                    status = ROW_MISMATCH
            else:
                gv = None
                status = ROW_MISSING
            rows.append({"path": path, "major": field, "minor": key,
                          "expected": ev, "generated": gv, "status": status})

        for key in sorted(set(gen_by_key.keys()) - set(exp_by_key.keys())):
            only_generated.append(f"{field}[{key}]")

    match = sum(1 for r in rows if r["status"] == ROW_MATCH)
    mismatch = sum(1 for r in rows if r["status"] == ROW_MISMATCH)
    missing = sum(1 for r in rows if r["status"] == ROW_MISSING)
    golden_total = match + mismatch + missing

    return {
        "file": "review",
        "status": "MATCH" if not mismatch and not missing and not only_generated else "MISMATCH",
        "golden_total": golden_total,
        "match_count": match,
        "mismatch_count": mismatch,
        "only_expected_count": missing,
        "only_generated_count": len(only_generated),
        "rows": rows,
        "only_generated": only_generated,
    }


# ---------------------------------------------------------------------------
# application_data comparison
# ---------------------------------------------------------------------------


def _form_no_sort_key(no_str: str) -> tuple:
    """フォーム項目番号でソート（"1", "2", "3.1", "23.5" 等を数値順に）。"""
    if not no_str:
        return (9999,)
    parts = no_str.replace(".", " ").split()
    result = []
    for p in parts:
        try:
            result.append(float(p))
        except ValueError:
            result.append(9999)
    return tuple(result)


def compare_application_data(gen: list, exp: list) -> dict:
    def row_key(item: dict) -> str:
        return item.get("canonical_path") or item.get("canonical_id") or ""

    gen_by_id = {row_key(it): it for it in gen if row_key(it)}
    exp_by_id = {row_key(it): it for it in exp if row_key(it)}

    rows: list[dict] = []
    only_generated: list[str] = []
    compare_keys = ("fill_value", "display_value")

    for cid in exp_by_id.keys():
        ev_item = exp_by_id[cid]
        if cid in gen_by_id:
            gv_item = gen_by_id[cid]
            all_match = True
            for ck in compare_keys:
                if not _values_match(gv_item.get(ck), ev_item.get(ck), cid):
                    all_match = False
            status = ROW_MATCH if all_match else ROW_MISMATCH
            gv_display = gv_item.get("fill_value", "")
        else:
            gv_item = {}
            gv_display = None
            # golden に値がなくて AI も出していない → 一致扱い
            # golden に値があって AI が出していない → 抽出漏れ
            ev_fill = ev_item.get("fill_value", "")
            if _normalise(ev_fill, cid) is None:
                status = ROW_MATCH
            else:
                status = ROW_MISSING

        # フォーム項目情報: golden 側を優先、なければ generated 側から取得
        form_no = (
            ev_item.get("display_no", "")
            or ev_item.get("no", "")
            or gv_item.get("display_no", "")
            or gv_item.get("no", "")
        )
        form_label = ev_item.get("label", "") or gv_item.get("label", "")
        form_field = f"{form_no} {form_label}".strip() if (form_no or form_label) else ""

        major, minor = _split_path(cid)
        rows.append({
            "path": cid,
            "major": major,
            "minor": minor,
            "form_field": form_field,
            "form_no": form_no,
            "expected": ev_item.get("fill_value", ""),
            "generated": gv_display,
            "status": status,
        })

    # フォーム項目番号順にソート
    rows.sort(key=lambda r: _form_no_sort_key(r.get("form_no", "")))

    for cid in sorted(set(gen_by_id.keys()) - set(exp_by_id.keys())):
        only_generated.append(cid)

    # golden_total: golden の全項目を母数に（空値も含む）
    golden_total = len(rows)
    match = sum(1 for r in rows if r["status"] == ROW_MATCH)
    mismatch = sum(1 for r in rows if r["status"] == ROW_MISMATCH)
    missing = sum(1 for r in rows if r["status"] == ROW_MISSING)

    return {
        "file": "application_data",
        "status": "MATCH" if not mismatch and not missing and not only_generated else "MISMATCH",
        "golden_total": golden_total,
        "match_count": match,
        "mismatch_count": mismatch,
        "only_expected_count": missing,
        "only_generated_count": len(only_generated),
        "rows": rows,
        "only_generated": only_generated,
    }


# ---------------------------------------------------------------------------
# File loading & pair matching
# ---------------------------------------------------------------------------

_FILE_PAIRS = [
    ("application_data.json", "application_data.golden.json", "application_data", compare_application_data),
    ("case_data.json", "case_data.golden.json", "case_data", compare_case_data),
    ("review.json", "review.golden.json", "review", compare_review),
]

_DEFAULT_TARGETS = ("case_data",)
_ALL_TARGETS = {"case_data", "application_data", "review"}


def _load_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR: Cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _load_case_data_pair(generated_dir: Path, expected_dir: Path) -> tuple[dict, dict]:
    gen_path = generated_dir / "case_data.json"
    exp_path = expected_dir / "case_data.golden.json"
    if not exp_path.exists():
        exp_path = expected_dir / "case_data.json"
    return _load_json(gen_path), _load_json(exp_path)


def _build_application_rows_pair(generated_dir: Path, expected_dir: Path) -> tuple[list[dict], list[dict]]:
    generated_case_data, expected_case_data = _load_case_data_pair(generated_dir, expected_dir)
    mapping_path = ROOT / "rasens-autofill/data/mappings/rasens_offer_mapping_v2.json"
    mapping_data = _load_json(mapping_path)
    return build_rows(generated_case_data, mapping_data), build_rows(expected_case_data, mapping_data)


def _parse_targets(value: str) -> list[str]:
    targets = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [target for target in targets if target not in _ALL_TARGETS]
    if unknown:
        print(f"ERROR: unknown target(s): {', '.join(unknown)}", file=sys.stderr)
        sys.exit(1)
    return targets


def run_comparison(generated_dir: Path, expected_dir: Path, targets: list[str]) -> list[dict]:
    results: list[dict] = []
    for gen_name, exp_name, label, compare_fn in _FILE_PAIRS:
        if label not in targets:
            continue
        if label == "application_data":
            if not (generated_dir / "case_data.json").exists():
                results.append({"file": label, "status": "MISSING", "reason": "generated case_data.json not found"})
                continue
            exp_case_data = expected_dir / "case_data.golden.json"
            if not exp_case_data.exists():
                results.append({"file": label, "status": "MISSING", "reason": "expected case_data.golden.json not found"})
                continue
            gen_data, exp_data = _build_application_rows_pair(generated_dir, expected_dir)
            results.append(compare_fn(gen_data, exp_data))
            continue

        gen_path = generated_dir / gen_name
        exp_path = expected_dir / exp_name
        if not exp_path.exists():
            exp_path = expected_dir / gen_name

        if not gen_path.exists() and not exp_path.exists():
            results.append({"file": label, "status": "SKIP", "reason": "both files absent"})
            continue
        if not gen_path.exists():
            results.append({"file": label, "status": "MISSING", "reason": f"generated file not found: {gen_name}"})
            continue
        if not exp_path.exists():
            results.append({"file": label, "status": "MISSING", "reason": f"expected file not found: {exp_name}"})
            continue

        gen_data = _load_json(gen_path)
        exp_data = _load_json(exp_path)
        if label == "case_data":
            results.append(compare_fn(gen_data, exp_data, _load_golden_manifest(expected_dir)))
        else:
            results.append(compare_fn(gen_data, exp_data))
    return results


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _escape_md(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def format_markdown(results: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Golden 比較レポート\n")

    agg_match = 0
    agg_golden_total = 0
    agg_mismatch = 0
    agg_missing = 0
    agg_extra = 0
    agg_application_only = 0
    agg_excluded = 0
    agg_needs_review = 0
    agg_unclassified = 0
    agg_manifest_unknown = 0

    problem_rows: list[tuple[str, dict]] = []
    config_errors: list[tuple[str, str]] = []
    for r in results:
        if r["status"] not in ("SKIP", "MISSING"):
            agg_match += r["match_count"]
            agg_golden_total += r["golden_total"]
            agg_mismatch += r["mismatch_count"]
            agg_missing += r["only_expected_count"]
            agg_extra += r["only_generated_count"]
            agg_application_only += r.get("application_only_count", 0)
            agg_excluded += r.get("excluded_count", 0)
            agg_needs_review += r.get("needs_review_count", 0)
            agg_unclassified += r.get("unclassified_count", 0)
            agg_manifest_unknown += r.get("manifest_unknown_path_count", 0)
            for row in r.get("rows", []):
                if row["status"] != ROW_MATCH:
                    problem_rows.append((r["file"], row))
            for error in r.get("config_errors", []):
                config_errors.append((r["file"], error))
            for path in r.get("only_generated", []):
                major, minor = _split_path(path)
                problem_rows.append((
                    r["file"],
                    {
                        "path": path,
                        "major": major,
                        "minor": minor,
                        "expected": "",
                        "generated": path,
                        "status": ROW_EXTRA,
                    },
                ))

    lines.append("## 判定\n")
    lines.append(("OK" if not problem_rows and not agg_extra and not agg_manifest_unknown and not config_errors else "NG") + "\n")
    lines.append("## 問題サマリ\n")
    lines.append("| 指標 | 件数 |")
    lines.append("|---|---:|")
    lines.append(f"| ✅ 一致 | {agg_match} |")
    lines.append(f"| ❌ 値の間違い | {agg_mismatch} |")
    lines.append(f"| ⚠️ 抽出漏れ | {agg_missing} |")
    lines.append(f"| ➕ 過剰抽出 | {agg_extra} |")
    if agg_application_only or agg_excluded or agg_needs_review or agg_unclassified or agg_manifest_unknown:
        lines.append(f"| 採点対象外: application_only | {agg_application_only} |")
        lines.append(f"| 採点対象外: excluded | {agg_excluded} |")
        lines.append(f"| 採点対象外: needs_review | {agg_needs_review} |")
        lines.append(f"| 採点対象外: unclassified | {agg_unclassified} |")
        lines.append(f"| manifest pathエラー | {agg_manifest_unknown} |")
    lines.append("")

    if problem_rows:
        lines.append("## 確認すべき項目\n")
        lines.append("| ファイル | 項目 | 大項目 | 小項目 | 正解データ | AI出力 | 判定 |")
        lines.append("|---|---|---|---|---|---|---|")
        for file_name, row in problem_rows:
            item = _escape_md(row.get("form_field", "") or row["path"])
            major = _escape_md(row["major"])
            minor = _escape_md(row["minor"])
            exp_val = _escape_md(_display(row["expected"]))
            gen_val = _escape_md(_display(row["generated"]))
            lines.append(f"| {file_name} | {item} | {major} | {minor} | {exp_val} | {gen_val} | {row['status']} |")
        lines.append("")

    if config_errors:
        lines.append("## 設定エラー\n")
        for file_name, error in config_errors:
            lines.append(f"- `{file_name}`: {_escape_md(error)}")
        lines.append("")

    lines.append("---\n")

    for r in results:
        lines.append(f"## {r['file']}\n")

        if r["status"] in ("SKIP", "MISSING"):
            lines.append(f"> {r.get('reason', '')}\n")
            continue
        if r["status"] == "CONFIG_ERROR":
            lines.append("> manifest設定に問題があります。採点結果として扱わず、設定を修正してください。\n")

        m_count = r["match_count"]
        mm_count = r["mismatch_count"]
        oe_count = r["only_expected_count"]
        og_count = r["only_generated_count"]
        g_total = r["golden_total"]

        accuracy = (m_count / g_total * 100) if g_total else 0
        lines.append(f"**Golden正答率: {accuracy:.1f}%** ({m_count}/{g_total} 項目)\n")
        mode = r.get("comparison_mode")
        if mode == "manifest_scoped":
            revision = r.get("manifest_revision_id") or "(none)"
            status = r.get("manifest_status") or "(none)"
            lines.append(f"比較モード: manifest scoped / revision: {revision} / status: {status}\n")
        elif mode == "legacy_all_fields":
            lines.append("比較モード: legacy all fields / manifestなし\n")
        for config_error in r.get("config_errors", []):
            lines.append(f"> CONFIG_ERROR: {_escape_md(config_error)}\n")
        lines.append(f"| 指標 | 件数 |")
        lines.append(f"|---|---|")
        lines.append(f"| ✅ 一致 | {m_count} |")
        lines.append(f"| ❌ 値の間違い | {mm_count} |")
        lines.append(f"| ⚠️ 抽出漏れ | {oe_count} |")
        lines.append(f"| ➕ 過剰抽出 | {og_count} |")
        if mode == "manifest_scoped":
            lines.append(f"| 採点対象外: application_only | {r.get('application_only_count', 0)} |")
            lines.append(f"| 採点対象外: excluded | {r.get('excluded_count', 0)} |")
            lines.append(f"| 採点対象外: needs_review | {r.get('needs_review_count', 0)} |")
            lines.append(f"| 採点対象外: unclassified | {r.get('unclassified_count', 0)} |")
            lines.append(f"| manifest pathエラー | {r.get('manifest_unknown_path_count', 0)} |")
        lines.append("")

        unknown_paths = r.get("manifest_unknown_paths") or []
        if unknown_paths:
            lines.append("### manifest pathエラー\n")
            for path in unknown_paths:
                lines.append(f"- `{_escape_md(path)}`")
            lines.append("")

        # Full detail table for golden fields
        has_form_field = any(row.get("form_field") for row in r.get("rows", []))
        lines.append("### 全項目詳細\n")
        if has_form_field:
            lines.append("| 申請フォーム項目 | 大項目 | 小項目 | 正解データ | AI出力 | 判定 |")
            lines.append("|---|---|---|---|---|---|")
        else:
            lines.append("| 大項目 | 小項目 | 正解データ | AI出力 | 判定 |")
            lines.append("|---|---|---|---|---|")

        for row in r.get("rows", []):
            major = _escape_md(row["major"])
            minor = _escape_md(row["minor"])
            exp_val = _escape_md(_display(row["expected"]))
            gen_val = _escape_md(_display(row["generated"]))
            status = row["status"]
            if has_form_field:
                form = _escape_md(row.get("form_field", ""))
                lines.append(f"| {form} | {major} | {minor} | {exp_val} | {gen_val} | {status} |")
            else:
                lines.append(f"| {major} | {minor} | {exp_val} | {gen_val} | {status} |")

        lines.append("")

    lines.append("## 全体サマリ\n")
    if agg_golden_total:
        overall = agg_match / agg_golden_total * 100
        lines.append(f"**Golden正答率（メイン指標）: {overall:.1f}%**\n")
        lines.append(f"正解が期待する **{agg_golden_total}** 項目のうち、"
                     f"AIが正しく抽出できたのは **{agg_match}** 項目\n")

    lines.append(f"| 指標 | 件数 |")
    lines.append(f"|---|---|")
    lines.append(f"| ✅ 一致 | {agg_match} |")
    lines.append(f"| ❌ 値の間違い | {agg_mismatch} |")
    lines.append(f"| ⚠️ 抽出漏れ | {agg_missing} |")
    lines.append(f"| ➕ 過剰抽出 | {agg_extra} |")
    if agg_application_only or agg_excluded or agg_needs_review or agg_unclassified or agg_manifest_unknown:
        lines.append(f"| 採点対象外: application_only | {agg_application_only} |")
        lines.append(f"| 採点対象外: excluded | {agg_excluded} |")
        lines.append(f"| 採点対象外: needs_review | {agg_needs_review} |")
        lines.append(f"| 採点対象外: unclassified | {agg_unclassified} |")
        lines.append(f"| manifest pathエラー | {agg_manifest_unknown} |")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare generated output with golden files")
    parser.add_argument("--generated", required=True, type=Path, help="Directory with generated files")
    parser.add_argument("--expected", required=True, type=Path, help="Directory with golden files")
    parser.add_argument("--targets", default=",".join(_DEFAULT_TARGETS), help="Comma-separated targets: case_data,application_data,review (default: case_data)")
    parser.add_argument("--output", type=Path, default=None, help="Write output to file (default: generated/comparison_report.md)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not args.generated.is_dir():
        print(f"ERROR: generated directory not found: {args.generated}", file=sys.stderr)
        sys.exit(1)
    if not args.expected.is_dir():
        print(f"ERROR: expected directory not found: {args.expected}", file=sys.stderr)
        sys.exit(1)

    results = run_comparison(args.generated, args.expected, _parse_targets(args.targets))

    # Default output path
    output_path = args.output or (args.generated / "comparison_report.md")

    if args.as_json:
        # Strip rows for JSON output (too verbose)
        json_results = []
        for r in results:
            jr = {k: v for k, v in r.items() if k != "rows"}
            json_results.append(jr)
        output_content = json.dumps(json_results, ensure_ascii=False, indent=2)
    else:
        output_content = format_markdown(results)

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_content, encoding="utf-8")

    # Print summary to stdout
    agg_match = sum(r.get("match_count", 0) for r in results if r["status"] not in ("SKIP", "MISSING"))
    agg_total = sum(r.get("golden_total", 0) for r in results if r["status"] not in ("SKIP", "MISSING"))
    rate = (agg_match / agg_total * 100) if agg_total else 0
    print(f"Golden正答率: {rate:.1f}% ({agg_match}/{agg_total})")
    print(f"レポート保存先: {output_path}")

    has_config_errors = any(r["status"] == "CONFIG_ERROR" for r in results)
    has_issues = any(r["status"] in ("MISMATCH", "MISSING", "CONFIG_ERROR") for r in results)
    if has_config_errors:
        sys.exit(2)
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
