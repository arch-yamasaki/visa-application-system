from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "run_experiment.py"
SPEC = importlib.util.spec_from_file_location("passport_routing_experiment", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ResponseValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = [
            {"document_id": "doc_001", "page_count": 2, "role": "bundle"},
            {"document_id": "doc_002", "page_count": 1, "role": "company"},
        ]

    def test_complete_coverage(self) -> None:
        response = {
            "documents": [
                {
                    "document_id": "doc_001",
                    "pages": [{"page_number": 1}, {"page_number": 2}],
                },
                {"document_id": "doc_002", "pages": [{"page_number": 1}]},
            ]
        }
        result = MODULE.validate_response(response, self.documents)
        self.assertTrue(result["valid"])
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["coverage_ratio"], 1.0)

    def test_missing_and_duplicate_pages_are_rejected(self) -> None:
        response = {
            "documents": [
                {
                    "document_id": "doc_001",
                    "pages": [{"page_number": 1}, {"page_number": 1}],
                },
                {"document_id": "doc_002", "pages": [{"page_number": 1}]},
            ]
        }
        result = MODULE.validate_response(response, self.documents)
        self.assertFalse(result["valid"])
        self.assertIn("duplicate_page", result["errors"])
        self.assertIn("missing_pages", result["errors"])


class SummaryTest(unittest.TestCase):
    def test_summary_keeps_only_routing_metadata(self) -> None:
        raw = {
            "api_success": True,
            "elapsed_ms": 123,
            "usage": {"prompt_tokens": 10, "candidate_tokens": 5},
            "validation": {"valid": True, "coverage_complete": True},
            "response": {
                "documents": [
                    {
                        "document_id": "doc_001",
                        "pages": [
                            {
                                "page_number": 1,
                                "document_type": "passport_identity_page",
                                "is_passport_identity_page": True,
                                "confidence": 98,
                                "needs_human_review": False,
                            }
                        ],
                    }
                ]
            },
        }
        config = {
            "id": "test",
            "model": "model",
            "thinking_level": "LOW",
            "media_resolution": "HIGH",
            "prompt_variant": "conservative",
            "temperature": None,
        }
        documents = [
            {"document_id": "doc_001", "page_count": 1, "role": "bundle"}
        ]
        summary = MODULE.safe_summary(raw, config, documents, "bundle", 1)
        self.assertEqual(summary["passport_candidates"][0]["document_ordinal"], 1)
        self.assertEqual(summary["metrics"]["recall"], 1.0)
        self.assertEqual(summary["metrics"]["precision"], 1.0)
        self.assertTrue(summary["metrics"]["page_set_exact_match"])
        self.assertNotIn("response", summary)

    def test_cost_estimate_uses_output_and_thinking_rates(self) -> None:
        usage = {
            "prompt_tokens": 1_000_000,
            "candidate_tokens": 100_000,
            "thought_tokens": 100_000,
        }
        self.assertEqual(MODULE.estimate_cost_usd("gemini-3.6-flash", usage), 3.0)


if __name__ == "__main__":
    unittest.main()
