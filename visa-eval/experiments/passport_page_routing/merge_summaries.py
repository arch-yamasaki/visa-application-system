#!/usr/bin/env python3
"""Merge PII-free experiment summaries and refresh pricing aggregates."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_experiment import (
    PRICING_RETRIEVED_DATE,
    PRICING_USD_PER_MILLION_TOKENS,
    aggregate_results,
    estimate_cost_usd,
    read_json,
    write_json,
)


def merge(paths: list[Path]) -> dict:
    artifacts = [read_json(path) for path in paths]
    results = []
    availability = {}
    for artifact in artifacts:
        if artifact.get("contains_pii") is not False:
            raise ValueError("refusing to merge an artifact not marked contains_pii=false")
        availability.update(artifact.get("model_availability", {}))
        results.extend(artifact.get("results", []))
    for result in results:
        result["estimated_usd"] = estimate_cost_usd(result["model"], result.get("usage"))
    return {
        "experiment": "passport_page_routing",
        "generated_at": max(artifact["generated_at"] for artifact in artifacts),
        "sdk": "google-genai",
        "model_availability": dict(sorted(availability.items())),
        "case_count": max(artifact.get("case_count", 0) for artifact in artifacts),
        "config_count": len({result["config_id"] for result in results}),
        "repetitions": max(artifact.get("repetitions", 1) for artifact in artifacts),
        "contains_pii": False,
        "pricing": {
            "currency": "USD",
            "retrieved_date": PRICING_RETRIEVED_DATE,
            "standard_rates_per_million_tokens": PRICING_USD_PER_MILLION_TOKENS,
            "formula": "(prompt_tokens * input_rate + (candidate_tokens + thought_tokens) * output_rate) / 1_000_000",
            "excludes": ["tax", "network", "storage", "other pipeline calls"],
        },
        "aggregates": aggregate_results(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_json(args.output, merge(args.summary))


if __name__ == "__main__":
    main()
