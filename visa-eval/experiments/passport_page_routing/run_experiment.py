#!/usr/bin/env python3
"""Evaluate PDF page classification before the main extraction pipeline.

Raw model responses stay below the git-ignored ``runs/`` directory. The optional
summary output contains only anonymized page coordinates, timings, token counts,
and document-type histograms.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parent
ROOT = EXPERIMENT_DIR.parents[2]
BACKEND = ROOT / "visa-app" / "backend"
DEFAULT_CONFIG = EXPERIMENT_DIR / "configs.json"
DEFAULT_RUNS = EXPERIMENT_DIR / "runs"

sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv(BACKEND / ".env")

DOCUMENT_TYPES = [
    "passport_identity_page",
    "passport_other_page",
    "residence_card",
    "immigration_application",
    "employment_terms",
    "company_registry",
    "company_financial_or_tax",
    "company_other",
    "diploma_or_certificate",
    "academic_transcript",
    "resume_or_work_history",
    "intake_form",
    "other",
    "unreadable",
]

TARGET_SCOPES = [
    "applicant_identity",
    "entry_plan",
    "immigration_history",
    "education",
    "employment_history",
    "employer",
    "employment",
    "review",
]

EVIDENCE_SIGNALS = [
    "mrz_visible",
    "passport_heading",
    "identity_layout",
    "passport_cover_or_visa_layout",
    "document_layout_only",
    "none",
]

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "documents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "page_count_observed": {"type": "integer"},
                    "pages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "page_number": {"type": "integer"},
                                "document_type": {
                                    "type": "string",
                                    "enum": DOCUMENT_TYPES,
                                },
                                "is_passport_identity_page": {"type": "boolean"},
                                "confidence": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 100,
                                },
                                "evidence_signals": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": EVIDENCE_SIGNALS,
                                    },
                                },
                                "target_scopes": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": TARGET_SCOPES,
                                    },
                                },
                                "needs_human_review": {"type": "boolean"},
                            },
                            "required": [
                                "page_number",
                                "document_type",
                                "is_passport_identity_page",
                                "confidence",
                                "evidence_signals",
                                "target_scopes",
                                "needs_human_review",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["document_id", "page_count_observed", "pages"],
                "additionalProperties": False,
            },
        },
        "has_ambiguous_passport_candidates": {"type": "boolean"},
    },
    "required": ["documents", "has_ambiguous_passport_candidates"],
    "additionalProperties": False,
}

PRICING_USD_PER_MILLION_TOKENS = {
    "gemini-3.6-flash": {"input": 1.50, "output_including_thinking": 7.50},
    "gemini-3.5-flash-lite": {"input": 0.30, "output_including_thinking": 2.50},
    "gemini-3-flash-preview": {"input": 0.50, "output_including_thinking": 3.00},
}
PRICING_RETRIEVED_DATE = "2026-08-09"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def short_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def resolve_manifest(fixture_dir: Path) -> Path:
    candidates = [
        fixture_dir / "input" / "document_manifest.json",
        fixture_dir / "document_manifest.blind.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"document manifest not found below {fixture_dir}")


def resolve_document_path(manifest: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    root_relative = ROOT / path
    if root_relative.exists():
        return root_relative
    return manifest.parent / path


def pdf_page_count(path: Path) -> int:
    completed = subprocess.run(
        ["pdfinfo", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in completed.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise ValueError(f"pdfinfo did not report page count for {path}")


def load_pdf_documents(fixture_dir: Path) -> list[dict[str, Any]]:
    manifest_path = resolve_manifest(fixture_dir)
    manifest = read_json(manifest_path)
    loaded = []
    for document in manifest.get("documents", []):
        if not document.get("use_as_input", True):
            continue
        path = resolve_document_path(manifest_path, document["path"])
        if path.suffix.lower() != ".pdf":
            continue
        if not path.exists():
            raise FileNotFoundError(path)
        loaded.append(
            {
                "document_id": f"doc_{len(loaded) + 1:03d}",
                "path": path,
                "page_count": pdf_page_count(path),
                "role": document.get("document_role", ""),
            }
        )
    if not loaded:
        raise ValueError("fixture contains no input PDF")
    return loaded


def build_prompt(documents: list[dict[str, Any]], variant: str) -> str:
    manifest_lines = "\n".join(
        f"- {document['document_id']}: expected physical pages={document['page_count']}"
        for document in documents
    )
    common = f"""You classify every physical page of the attached PDF documents before visa-data extraction.

Documents:
{manifest_lines}

Return exactly one page object for every page, numbered from 1 inside each PDF.
Never output names, dates of birth, passport numbers, addresses, quotes, transcriptions, or any other document contents.
Use only the allowed document types, evidence signals, target scopes, confidence, and review flag in the schema.
Mark is_passport_identity_page=true only for the passport biographical/identity page containing the holder portrait/details and normally an MRZ. A passport cover, visa page, stamps, or residence card is not an identity page.
The target_scopes field is advisory routing. Include review whenever a page is unreadable or classification is uncertain.
"""
    if variant == "concise":
        return common + "Classify independently and return the structured result."
    if variant == "conservative":
        return common + """
Optimize passport identity-page recall without inventing a positive result. If an identity page is plausible but unclear, keep it as a passport candidate, lower confidence, and set needs_human_review=true. Do not omit uncertain pages and do not use one uncertain page to exclude all other candidates. Check that the returned page coverage exactly matches every expected physical page count before responding.
"""
    raise ValueError(f"unknown prompt variant: {variant}")


def enum_value(enum_type: Any, value: str) -> Any:
    try:
        return getattr(enum_type, value.upper())
    except AttributeError as exc:
        raise ValueError(f"unsupported {enum_type.__name__}: {value}") from exc


def create_parts(documents: list[dict[str, Any]], media_resolution: str) -> list[types.Part]:
    resolution = enum_value(types.PartMediaResolutionLevel, f"MEDIA_RESOLUTION_{media_resolution}")
    parts: list[types.Part] = []
    for document in documents:
        parts.append(types.Part.from_text(text=f"BEGIN {document['document_id']}"))
        parts.append(
            types.Part.from_bytes(
                data=document["path"].read_bytes(),
                mime_type="application/pdf",
                media_resolution=resolution,
            )
        )
        parts.append(types.Part.from_text(text=f"END {document['document_id']}"))
    return parts


def usage_value(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) else None


def estimate_cost_usd(model: str, usage: dict[str, int | None] | None) -> float | None:
    price = PRICING_USD_PER_MILLION_TOKENS.get(model)
    if not price or not usage or usage.get("prompt_tokens") is None:
        return None
    output_tokens = (usage.get("candidate_tokens") or 0) + (usage.get("thought_tokens") or 0)
    cost = (
        usage["prompt_tokens"] * price["input"]
        + output_tokens * price["output_including_thinking"]
    ) / 1_000_000
    return round(cost, 6)


def validate_response(data: Any, documents: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {document["document_id"]: document["page_count"] for document in documents}
    returned: dict[str, set[int]] = {key: set() for key in expected}
    errors: list[str] = []
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list):
        return {
            "valid": False,
            "coverage_complete": False,
            "coverage_ratio": 0.0,
            "errors": ["invalid_top_level"],
        }
    for document in data["documents"]:
        document_id = document.get("document_id")
        if document_id not in expected:
            errors.append("unknown_document_id")
            continue
        for page in document.get("pages", []):
            number = page.get("page_number")
            if not isinstance(number, int) or not 1 <= number <= expected[document_id]:
                errors.append("out_of_range_page")
                continue
            if number in returned[document_id]:
                errors.append("duplicate_page")
            returned[document_id].add(number)
    expected_total = sum(expected.values())
    returned_total = sum(len(pages) for pages in returned.values())
    missing = sum(expected[key] - len(returned[key]) for key in expected)
    if missing:
        errors.append("missing_pages")
    return {
        "valid": not errors,
        "coverage_complete": missing == 0 and returned_total == expected_total,
        "coverage_ratio": round(returned_total / expected_total, 4),
        "errors": sorted(set(errors)),
    }


def safe_summary(
    raw: dict[str, Any],
    config: dict[str, Any],
    documents: list[dict[str, Any]],
    ground_truth_role: str | None,
    ground_truth_page: int | None,
) -> dict[str, Any]:
    response = raw.get("response") or {}
    usage = raw.get("usage")
    page_types: Counter[str] = Counter()
    candidates = []
    document_ordinals = {
        document["document_id"]: index
        for index, document in enumerate(documents, start=1)
    }
    for document in response.get("documents", []):
        for page in document.get("pages", []):
            page_types[str(page.get("document_type", "unknown"))] += 1
            if page.get("is_passport_identity_page"):
                candidates.append(
                    {
                        "document_ordinal": document_ordinals.get(document.get("document_id")),
                        "page_number": page.get("page_number"),
                        "confidence": page.get("confidence"),
                        "needs_human_review": page.get("needs_human_review"),
                    }
                )
    ground_truth = None
    if ground_truth_role and ground_truth_page:
        document = next((item for item in documents if item["role"] == ground_truth_role), None)
        if document:
            ground_truth = {
                "document_ordinal": document_ordinals[document["document_id"]],
                "page_number": ground_truth_page,
                "label_source": "human_visual_review_of_pixelated_contact_sheet",
            }
    predicted_coordinates = {
        (item.get("document_ordinal"), item.get("page_number")) for item in candidates
    }
    metrics = None
    if ground_truth:
        expected_coordinates = {
            (ground_truth["document_ordinal"], ground_truth["page_number"])
        }
        true_positive = len(predicted_coordinates & expected_coordinates)
        false_positive = len(predicted_coordinates - expected_coordinates)
        false_negative = len(expected_coordinates - predicted_coordinates)
        metrics = {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": (
                round(true_positive / (true_positive + false_positive), 4)
                if true_positive + false_positive
                else 0.0
            ),
            "recall": round(true_positive / (true_positive + false_negative), 4),
            "page_set_exact_match": predicted_coordinates == expected_coordinates,
        }
    return {
        "config_id": config["id"],
        "model": config["model"],
        "thinking_level": config["thinking_level"],
        "media_resolution": config["media_resolution"],
        "prompt_variant": config["prompt_variant"],
        "temperature_mode": "omitted" if config.get("temperature") is None else "explicit_zero",
        "api_success": raw.get("api_success", False),
        "schema_validation": raw.get("validation"),
        "elapsed_ms": raw.get("elapsed_ms"),
        "usage": usage,
        "estimated_usd": estimate_cost_usd(config["model"], usage),
        "finish_reason": raw.get("finish_reason"),
        "input_pdf_count": len(documents),
        "input_page_count": sum(item["page_count"] for item in documents),
        "document_type_histogram": dict(sorted(page_types.items())),
        "passport_candidates": candidates,
        "ground_truth": ground_truth,
        "metrics": metrics,
        "error_type": raw.get("error_type"),
    }


def aggregate_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(result["config_id"], []).append(result)
    aggregates = []
    for config_id, rows in sorted(grouped.items()):
        successful = [row for row in rows if row.get("api_success")]
        complete = [
            row
            for row in rows
            if (row.get("schema_validation") or {}).get("coverage_complete")
        ]
        metrics = [row["metrics"] for row in rows if row.get("metrics")]
        successful_metrics = [
            row["metrics"]
            for row in successful
            if row.get("metrics")
        ]
        tp = sum(item["true_positive"] for item in metrics)
        fp = sum(item["false_positive"] for item in metrics)
        fn = sum(item["false_negative"] for item in metrics)
        successful_tp = sum(item["true_positive"] for item in successful_metrics)
        successful_fp = sum(item["false_positive"] for item in successful_metrics)
        successful_fn = sum(item["false_negative"] for item in successful_metrics)
        elapsed = [row["elapsed_ms"] for row in successful if row.get("elapsed_ms") is not None]
        total_tokens = [
            row["usage"]["total_tokens"]
            for row in successful
            if row.get("usage") and row["usage"].get("total_tokens") is not None
        ]
        costs = [row["estimated_usd"] for row in successful if row.get("estimated_usd") is not None]
        first = rows[0]
        aggregates.append(
            {
                "config_id": config_id,
                "model": first["model"],
                "thinking_level": first["thinking_level"],
                "media_resolution": first["media_resolution"],
                "prompt_variant": first["prompt_variant"],
                "temperature_mode": first["temperature_mode"],
                "runs": len(rows),
                "api_success_rate": round(len(successful) / len(rows), 4),
                "coverage_complete_rate": round(len(complete) / len(rows), 4),
                "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
                "recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
                "classification_precision_when_api_successful": (
                    round(successful_tp / (successful_tp + successful_fp), 4)
                    if successful_tp + successful_fp
                    else 0.0
                ),
                "classification_recall_when_api_successful": (
                    round(successful_tp / (successful_tp + successful_fn), 4)
                    if successful_tp + successful_fn
                    else 0.0
                ),
                "classification_exact_match_rate_when_api_successful": (
                    round(
                        sum(item["page_set_exact_match"] for item in successful_metrics)
                        / len(successful_metrics),
                        4,
                    )
                    if successful_metrics
                    else None
                ),
                "page_set_exact_match_rate": (
                    round(sum(item["page_set_exact_match"] for item in metrics) / len(metrics), 4)
                    if metrics
                    else None
                ),
                "mean_elapsed_ms": round(sum(elapsed) / len(elapsed)) if elapsed else None,
                "mean_total_tokens": round(sum(total_tokens) / len(total_tokens)) if total_tokens else None,
                "mean_estimated_usd": round(sum(costs) / len(costs), 6) if costs else None,
            }
        )
    return aggregates


def run_one(
    client: genai.Client,
    config: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    generation: dict[str, Any] = {
        "response_mime_type": "application/json",
        "response_json_schema": RESPONSE_SCHEMA,
        "max_output_tokens": 16384,
        "thinking_config": types.ThinkingConfig(
            thinking_level=enum_value(types.ThinkingLevel, config["thinking_level"])
        ),
    }
    if config.get("temperature") is not None:
        generation["temperature"] = config["temperature"]
    content = types.Content(
        role="user",
        parts=[
            *create_parts(documents, config["media_resolution"]),
            types.Part.from_text(text=build_prompt(documents, config["prompt_variant"])),
        ],
    )
    started = time.monotonic()
    try:
        response = client.models.generate_content(
            model=config["model"],
            contents=[content],
            config=types.GenerateContentConfig(**generation),
        )
        elapsed_ms = round((time.monotonic() - started) * 1000)
        parsed = json.loads(response.text)
        usage = getattr(response, "usage_metadata", None)
        candidate = response.candidates[0] if response.candidates else None
        finish_reason = getattr(candidate, "finish_reason", None) if candidate else None
        return {
            "api_success": True,
            "elapsed_ms": elapsed_ms,
            "usage": {
                "prompt_tokens": usage_value(usage, "prompt_token_count"),
                "candidate_tokens": usage_value(usage, "candidates_token_count"),
                "thought_tokens": usage_value(usage, "thoughts_token_count"),
                "total_tokens": usage_value(usage, "total_token_count"),
            },
            "finish_reason": str(finish_reason) if finish_reason else None,
            "validation": validate_response(parsed, documents),
            "response": parsed,
        }
    except Exception as exc:
        return {
            "api_success": False,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error_type": type(exc).__name__,
        }


def load_configs(path: Path, selected: set[str]) -> list[dict[str, Any]]:
    configs = read_json(path).get("configs", [])
    if selected:
        configs = [config for config in configs if config.get("id") in selected]
        missing = selected - {config.get("id") for config in configs}
        if missing:
            raise ValueError(f"unknown config ids: {sorted(missing)}")
    return configs


def model_availability(client: genai.Client, configs: list[dict[str, Any]]) -> dict[str, bool]:
    result = {}
    for model in sorted({config["model"] for config in configs}):
        try:
            client.models.get(model=model)
            result[model] = True
        except Exception:
            result[model] = False
    return result


def run(args: argparse.Namespace) -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit("GOOGLE_API_KEY is not configured")
    configs = load_configs(args.config_file, set(args.config_id))
    client = genai.Client(http_options=types.HttpOptions(timeout=args.timeout_ms))
    availability = model_availability(client, configs)
    if args.check_models:
        for model, available in availability.items():
            print(f"{model}: {'available' if available else 'unavailable'}")
        return
    fixtures = [path.resolve() for path in args.fixture_dir]
    run_dir = (args.output_dir or DEFAULT_RUNS / datetime.now().strftime("%Y%m%d_%H%M%S")).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for case_index, fixture in enumerate(fixtures, start=1):
        documents = load_pdf_documents(fixture)
        case_id = f"case_{case_index:03d}"
        for config in configs:
            for repetition in range(1, args.repetitions + 1):
                print(
                    f"running case={case_id} config={config['id']} repetition={repetition}",
                    flush=True,
                )
                raw = run_one(client, config, documents)
                write_json(
                    run_dir / case_id / f"{config['id']}.repeat_{repetition:02d}.raw.json",
                    raw,
                )
                summary = safe_summary(
                    raw,
                    config,
                    documents,
                    args.ground_truth_document_role,
                    args.ground_truth_page,
                )
                summary["case_ordinal"] = case_index
                summary["repetition"] = repetition
                summaries.append(summary)
                print(
                    "completed success=%s coverage=%s candidates=%d elapsed_ms=%s"
                    % (
                        summary["api_success"],
                        (summary.get("schema_validation") or {}).get("coverage_complete"),
                        len(summary["passport_candidates"]),
                        summary["elapsed_ms"],
                    ),
                    flush=True,
                )
    artifact = {
        "experiment": "passport_page_routing",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sdk": "google-genai",
        "model_availability": availability,
        "case_count": len(fixtures),
        "config_count": len(configs),
        "repetitions": args.repetitions,
        "contains_pii": False,
        "pricing": {
            "currency": "USD",
            "retrieved_date": PRICING_RETRIEVED_DATE,
            "standard_rates_per_million_tokens": PRICING_USD_PER_MILLION_TOKENS,
            "formula": "(prompt_tokens * input_rate + (candidate_tokens + thought_tokens) * output_rate) / 1_000_000",
            "excludes": ["tax", "network", "storage", "other pipeline calls"],
        },
        "aggregates": aggregate_results(summaries),
        "results": summaries,
    }
    write_json(run_dir / "summary.json", artifact)
    if args.summary_output:
        write_json(args.summary_output.resolve(), artifact)
    print(f"wrote anonymized summary: {args.summary_output or run_dir / 'summary.json'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_dir", type=Path, nargs="*")
    parser.add_argument("--config-file", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--config-id", action="append", default=[])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--ground-truth-document-role")
    parser.add_argument("--ground-truth-page", type=int)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--timeout-ms", type=int, default=300_000)
    parser.add_argument("--check-models", action="store_true")
    args = parser.parse_args()
    if not args.check_models and not args.fixture_dir:
        parser.error("fixture_dir is required unless --check-models is used")
    run(args)


if __name__ == "__main__":
    main()
