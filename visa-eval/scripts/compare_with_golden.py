#!/usr/bin/env python3
"""Compare generated output with golden (expected) files.

Usage:
    python visa-eval/scripts/compare_with_golden.py \
        --generated <generated_dir> \
        --expected <expected_dir> \
        [--targets case_data,application_data] [--output <file>] [--json]

If --output is omitted, the report is saved to <generated_dir>/comparison_report.md
and a summary is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
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


def _normalise(value: Any) -> Any:
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


def _display(value: Any, max_len: int = 60) -> str:
    """Format a value for table display."""
    if value is None:
        return ""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s


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
        ev_norm = _normalise(ev)
        major, minor = _split_path(key)

        if key in gen_flat:
            gv = gen_flat[key]
            gv_norm = _normalise(gv)
            if gv_norm == ev_norm:
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


def compare_case_data(gen: dict, exp: dict) -> dict:
    gen_flat = _flatten(gen, skip_keys=_SKIP_KEYS_CASE_DATA)
    exp_flat = _flatten(exp, skip_keys=_SKIP_KEYS_CASE_DATA)

    rows = _build_golden_rows(gen_flat, exp_flat)
    match = sum(1 for r in rows if r["status"] == ROW_MATCH)
    mismatch = sum(1 for r in rows if r["status"] == ROW_MISMATCH)
    missing = sum(1 for r in rows if r["status"] == ROW_MISSING)

    # Extra: in generated but not in expected (non-empty only)
    extra_keys = sorted(set(gen_flat.keys()) - set(exp_flat.keys()))
    extra = [k for k in extra_keys if _normalise(gen_flat[k]) is not None]

    golden_total = match + mismatch + missing
    return {
        "file": "case_data",
        "status": "MATCH" if not mismatch and not missing and not extra else "MISMATCH",
        "golden_total": golden_total,
        "match_count": match,
        "mismatch_count": mismatch,
        "only_expected_count": missing,
        "only_generated_count": len(extra),
        "rows": rows,
        "only_generated": extra,
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
        status = ROW_MATCH if _normalise(gv) == _normalise(ev) else ROW_MISMATCH
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
                if _normalise(gv_item.get(ck)) != _normalise(ev_item.get(ck)):
                    all_match = False
            status = ROW_MATCH if all_match else ROW_MISMATCH
            gv_display = gv_item.get("fill_value", "")
        else:
            gv_item = {}
            gv_display = None
            # golden に値がなくて AI も出していない → 一致扱い
            # golden に値があって AI が出していない → 抽出漏れ
            ev_fill = ev_item.get("fill_value", "")
            if _normalise(ev_fill) is None:
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

_DEFAULT_TARGETS = ("case_data", "application_data")
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
    if not gen_path.exists():
        gen_path = generated_dir / "case_data.golden.json"
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
            if not (generated_dir / "case_data.json").exists() and not (generated_dir / "case_data.golden.json").exists():
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
        if not gen_path.exists():
            gen_path = generated_dir / exp_name
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

    problem_rows: list[tuple[str, dict]] = []
    for r in results:
        if r["status"] not in ("SKIP", "MISSING"):
            agg_match += r["match_count"]
            agg_golden_total += r["golden_total"]
            agg_mismatch += r["mismatch_count"]
            agg_missing += r["only_expected_count"]
            agg_extra += r["only_generated_count"]
            for row in r.get("rows", []):
                if row["status"] != ROW_MATCH:
                    problem_rows.append((r["file"], row))
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
    lines.append(("OK" if not problem_rows and not agg_extra else "NG") + "\n")
    lines.append("## 問題サマリ\n")
    lines.append("| 指標 | 件数 |")
    lines.append("|---|---:|")
    lines.append(f"| ✅ 一致 | {agg_match} |")
    lines.append(f"| ❌ 値の間違い | {agg_mismatch} |")
    lines.append(f"| ⚠️ 抽出漏れ | {agg_missing} |")
    lines.append(f"| ➕ 過剰抽出 | {agg_extra} |")
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

    lines.append("---\n")

    for r in results:
        lines.append(f"## {r['file']}\n")

        if r["status"] in ("SKIP", "MISSING"):
            lines.append(f"> {r.get('reason', '')}\n")
            continue

        m_count = r["match_count"]
        mm_count = r["mismatch_count"]
        oe_count = r["only_expected_count"]
        og_count = r["only_generated_count"]
        g_total = r["golden_total"]

        accuracy = (m_count / g_total * 100) if g_total else 0
        lines.append(f"**Golden正答率: {accuracy:.1f}%** ({m_count}/{g_total} 項目)\n")
        lines.append(f"| 指標 | 件数 |")
        lines.append(f"|---|---|")
        lines.append(f"| ✅ 一致 | {m_count} |")
        lines.append(f"| ❌ 値の間違い | {mm_count} |")
        lines.append(f"| ⚠️ 抽出漏れ | {oe_count} |")
        lines.append(f"| ➕ 過剰抽出 | {og_count} |")
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

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare generated output with golden files")
    parser.add_argument("--generated", required=True, type=Path, help="Directory with generated files")
    parser.add_argument("--expected", required=True, type=Path, help="Directory with golden files")
    parser.add_argument("--targets", default=",".join(_DEFAULT_TARGETS), help="Comma-separated targets: case_data,application_data,review")
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

    has_issues = any(r["status"] in ("MISMATCH", "MISSING") for r in results)
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
