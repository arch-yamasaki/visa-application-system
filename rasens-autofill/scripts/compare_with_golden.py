#!/usr/bin/env python3
"""Compare generated output with golden (expected) files.

Usage:
    python3 scripts/compare_with_golden.py \
        --generated <generated_dir> \
        --expected <expected_dir> \
        [--output <file>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_EMPTY_SYNONYMS = {None, "", "unknown", "n/a", "na", "null"}
_SKIP_KEYS_CASE_DATA = {"source_refs", "field_metadata", "schema_version"}


def _normalise(value: Any) -> Any:
    """Normalise a scalar so that null / empty / unknown / NA compare equal."""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _EMPTY_SYNONYMS:
            return None
        return value.strip()
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return value


# ---------------------------------------------------------------------------
# Flatten nested JSON to dot-path dict
# ---------------------------------------------------------------------------


def _flatten(obj: Any, prefix: str = "", skip_keys: set[str] | None = None) -> dict[str, Any]:
    """Flatten a nested dict/list into {dot.path: scalar_value}."""
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


# ---------------------------------------------------------------------------
# case_data comparison
# ---------------------------------------------------------------------------


def compare_case_data(gen: dict, exp: dict) -> dict:
    gen_flat = _flatten(gen, skip_keys=_SKIP_KEYS_CASE_DATA)
    exp_flat = _flatten(exp, skip_keys=_SKIP_KEYS_CASE_DATA)

    all_keys = sorted(set(gen_flat) | set(exp_flat))
    matches: list[str] = []
    mismatches: list[dict] = []
    only_expected: list[str] = []
    only_generated: list[str] = []

    for k in all_keys:
        in_gen = k in gen_flat
        in_exp = k in exp_flat
        if in_gen and in_exp:
            gv = _normalise(gen_flat[k])
            ev = _normalise(exp_flat[k])
            if gv == ev:
                matches.append(k)
            else:
                mismatches.append({"path": k, "generated": gen_flat[k], "expected": exp_flat[k]})
        elif in_exp and not in_gen:
            # only count as missing if the expected value is non-empty
            if _normalise(exp_flat[k]) is not None:
                only_expected.append(k)
            else:
                matches.append(k)  # both effectively empty
        else:
            if _normalise(gen_flat[k]) is not None:
                only_generated.append(k)
            else:
                matches.append(k)

    total = len(matches) + len(mismatches) + len(only_expected) + len(only_generated)
    return {
        "file": "case_data",
        "status": "MATCH" if not mismatches and not only_expected and not only_generated else "MISMATCH",
        "total_fields": total,
        "match_count": len(matches),
        "mismatch_count": len(mismatches),
        "only_expected_count": len(only_expected),
        "only_generated_count": len(only_generated),
        "mismatches": mismatches,
        "only_expected": only_expected,
        "only_generated": only_generated,
    }


# ---------------------------------------------------------------------------
# review comparison
# ---------------------------------------------------------------------------

_REVIEW_EXACT_KEYS = {"case_id", "expected_route"}
_REVIEW_SET_FIELDS = {"missing_documents", "missing_items", "validation_errors", "findings", "assessments"}
_REVIEW_SKIP_KEYS = {"schema_version", "golden_status", "expected_workflow_state"}


def _set_key(item: Any) -> str:
    """Build a hashable key for a list item in review arrays."""
    if isinstance(item, dict):
        # Use path or code as primary key, fall back to sorted JSON
        for k in ("path", "code", "type"):
            if k in item:
                return f"{k}={item[k]}"
        return json.dumps(item, sort_keys=True, ensure_ascii=False)
    return str(item)


def compare_review(gen: dict, exp: dict) -> dict:
    matches: list[str] = []
    mismatches: list[dict] = []
    only_expected: list[str] = []
    only_generated: list[str] = []

    # Exact-match keys
    for k in _REVIEW_EXACT_KEYS:
        gv = gen.get(k)
        ev = exp.get(k)
        if _normalise(gv) == _normalise(ev):
            matches.append(k)
        else:
            mismatches.append({"path": k, "generated": gv, "expected": ev})

    # Set-compare array fields
    for field in _REVIEW_SET_FIELDS:
        gen_list = gen.get(field, []) or []
        exp_list = exp.get(field, []) or []
        gen_by_key = {_set_key(it): it for it in gen_list}
        exp_by_key = {_set_key(it): it for it in exp_list}

        for key in sorted(set(gen_by_key) | set(exp_by_key)):
            path = f"{field}[{key}]"
            if key in gen_by_key and key in exp_by_key:
                if json.dumps(gen_by_key[key], sort_keys=True) == json.dumps(exp_by_key[key], sort_keys=True):
                    matches.append(path)
                else:
                    mismatches.append({"path": path, "generated": gen_by_key[key], "expected": exp_by_key[key]})
            elif key in exp_by_key:
                only_expected.append(path)
            else:
                only_generated.append(path)

    total = len(matches) + len(mismatches) + len(only_expected) + len(only_generated)
    return {
        "file": "review",
        "status": "MATCH" if not mismatches and not only_expected and not only_generated else "MISMATCH",
        "total_fields": total,
        "match_count": len(matches),
        "mismatch_count": len(mismatches),
        "only_expected_count": len(only_expected),
        "only_generated_count": len(only_generated),
        "mismatches": mismatches,
        "only_expected": only_expected,
        "only_generated": only_generated,
    }


# ---------------------------------------------------------------------------
# application_data comparison
# ---------------------------------------------------------------------------

_APP_SKIP_KEYS = {"section", "no", "label", "notes"}


def compare_application_data(gen: list, exp: list) -> dict:
    gen_by_id = {it.get("canonical_id"): it for it in gen if it.get("canonical_id")}
    exp_by_id = {it.get("canonical_id"): it for it in exp if it.get("canonical_id")}

    all_ids = sorted(set(gen_by_id) | set(exp_by_id))
    matches: list[str] = []
    mismatches: list[dict] = []
    only_expected: list[str] = []
    only_generated: list[str] = []

    compare_keys = {"fill_value", "display_value"}

    for cid in all_ids:
        in_gen = cid in gen_by_id
        in_exp = cid in exp_by_id
        if in_gen and in_exp:
            diffs: dict[str, dict] = {}
            for ck in compare_keys:
                gv = _normalise(gen_by_id[cid].get(ck))
                ev = _normalise(exp_by_id[cid].get(ck))
                if gv != ev:
                    diffs[ck] = {"generated": gen_by_id[cid].get(ck), "expected": exp_by_id[cid].get(ck)}
            if diffs:
                mismatches.append({"canonical_id": cid, "diffs": diffs})
            else:
                matches.append(cid)
        elif in_exp:
            only_expected.append(cid)
        else:
            only_generated.append(cid)

    total = len(matches) + len(mismatches) + len(only_expected) + len(only_generated)
    return {
        "file": "application_data",
        "status": "MATCH" if not mismatches and not only_expected and not only_generated else "MISMATCH",
        "total_fields": total,
        "match_count": len(matches),
        "mismatch_count": len(mismatches),
        "only_expected_count": len(only_expected),
        "only_generated_count": len(only_generated),
        "mismatches": mismatches,
        "only_expected": only_expected,
        "only_generated": only_generated,
    }


# ---------------------------------------------------------------------------
# File loading & pair matching
# ---------------------------------------------------------------------------

_FILE_PAIRS = [
    ("case_data.json", "case_data.golden.json", "case_data", compare_case_data),
    ("review.json", "review.golden.json", "review", compare_review),
    ("application_data.json", "application_data.golden.json", "application_data", compare_application_data),
]


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


def run_comparison(generated_dir: Path, expected_dir: Path) -> list[dict]:
    results: list[dict] = []

    for gen_name, exp_name, label, compare_fn in _FILE_PAIRS:
        gen_path = generated_dir / gen_name
        # Also accept golden-suffixed names in generated dir (self-comparison)
        if not gen_path.exists():
            gen_path = generated_dir / exp_name

        exp_path = expected_dir / exp_name
        # Also accept non-golden names in expected dir
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
        result = compare_fn(gen_data, exp_data)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_text(results: list[dict]) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Golden Comparison Report")
    lines.append("=" * 60)

    total_match = 0
    total_fields = 0
    total_mismatch = 0
    total_missing = 0

    for r in results:
        lines.append("")
        lines.append(f"--- {r['file']} ---")
        status = r["status"]
        lines.append(f"  Status: {status}")

        if status in ("SKIP", "MISSING"):
            lines.append(f"  Reason: {r.get('reason', '')}")
            continue

        mc = r["match_count"]
        tf = r["total_fields"]
        lines.append(f"  Fields: {tf}  Match: {mc}  Mismatch: {r['mismatch_count']}  "
                      f"OnlyExpected: {r['only_expected_count']}  OnlyGenerated: {r['only_generated_count']}")

        total_match += mc
        total_fields += tf
        total_mismatch += r["mismatch_count"]
        total_missing += r["only_expected_count"]

        if r.get("mismatches"):
            lines.append("  Mismatches:")
            for m in r["mismatches"]:
                if "path" in m:
                    lines.append(f"    {m['path']}")
                    lines.append(f"      expected : {m['expected']}")
                    lines.append(f"      generated: {m['generated']}")
                elif "canonical_id" in m:
                    lines.append(f"    {m['canonical_id']}")
                    for dk, dv in m["diffs"].items():
                        lines.append(f"      {dk}: expected={dv['expected']}  generated={dv['generated']}")

        if r.get("only_expected"):
            lines.append("  Only in expected:")
            for p in r["only_expected"]:
                lines.append(f"    {p}")

        if r.get("only_generated"):
            lines.append("  Only in generated:")
            for p in r["only_generated"]:
                lines.append(f"    {p}")

    lines.append("")
    lines.append("=" * 60)
    rate = (total_match / total_fields * 100) if total_fields else 0
    lines.append(f"Summary: {total_match}/{total_fields} fields match ({rate:.1f}%)  "
                 f"mismatches={total_mismatch}  missing={total_missing}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare generated output with golden files")
    parser.add_argument("--generated", required=True, type=Path, help="Directory with generated files")
    parser.add_argument("--expected", required=True, type=Path, help="Directory with golden files")
    parser.add_argument("--output", type=Path, default=None, help="Write output to file")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not args.generated.is_dir():
        print(f"ERROR: generated directory not found: {args.generated}", file=sys.stderr)
        sys.exit(1)
    if not args.expected.is_dir():
        print(f"ERROR: expected directory not found: {args.expected}", file=sys.stderr)
        sys.exit(1)

    results = run_comparison(args.generated, args.expected)

    if args.as_json:
        output = json.dumps(results, ensure_ascii=False, indent=2)
    else:
        output = format_text(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"Output written to {args.output}")
    else:
        print(output)

    # Exit with code 1 if any MISMATCH or MISSING
    has_issues = any(r["status"] in ("MISMATCH", "MISSING") for r in results)
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
