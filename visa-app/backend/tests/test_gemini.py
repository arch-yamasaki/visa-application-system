"""extractors.gemini のユニットテスト。Gemini API はモックで置き換え。"""

import json
from unittest.mock import MagicMock, patch

import pytest

from extractors.gemini import (
    _build_ocr_context,
    _call_gemini,
    _extract_field_metadata,
    _extract_display_values,
    _build_extraction_result,
    _unflatten_field_values,
    _uses_raw_source_refs,
    _map_field_metadata,
    _normalize_passport_identity_candidates,
    _iso_birth_date,
    EXTRACTION_SCOPES,
    extract_all_scopes,
    extract_pdf_direct,
    extract_text_only,
    extract_with_images,
)
from application_data import build_application_data
from extractors.prompt_template import build_extraction_prompt, build_scoped_prompt
from extractors.types import (
    BoundingBox,
    ExtractionResult,
    OcrResult,
    PageResult,
    WordResult,
)

# ---------- テスト用データ -----------------------------------------------

_CASE_META = {
    "case_id": "case_test01",
    "application_type": "certificate_of_eligibility",
    "target_status": "engineer_humanities_international",
}

_DOCUMENTS = [
    {
        "file_name": "passport.pdf",
        "document_role": "passport",
        "document_id": "doc_p",
        "document_kind": "pdf",
        "page_count": 1,
    },
    {
        "file_name": "diploma.pdf",
        "document_role": "education",
        "document_id": "doc_d",
    },
]

# 新形式（FieldValue 構造）の Gemini レスポンス
_GEMINI_RESPONSE_NEW = {
    "case_data": {
        "applicant": {
            "name_roman": {
                "value": "TANAKA TARO",
                "source_ref": {
                    "document_id": "doc_p",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.95,
                },
            },
            "nationality_region": {
                "value": "JP",
                "source_ref": {
                    "document_id": "doc_p",
                    "page": 1,
                    "text_quote": "JP",
                    "confidence": 0.9,
                },
            },
        },
    },
    "review": {
        "missing_items": [],
        "summary": "問題なし",
    },
}


def _make_ocr_results() -> list[OcrResult]:
    return [
        OcrResult(
            document_id="doc_p",
            pages=[
                PageResult(
                    page_number=1,
                    text="TANAKA TARO JP passport",
                    words=[
                        WordResult(
                            text="TANAKA",
                            bbox=BoundingBox(x=10, y=20, width=80, height=15),
                            confidence=1.0,
                        ),
                        WordResult(
                            text="TARO",
                            bbox=BoundingBox(x=100, y=20, width=60, height=15),
                            confidence=1.0,
                        ),
                    ],
                )
            ],
        )
    ]


def _mock_gemini_response(raw: dict):
    """_call_gemini が返す値をモックするためのレスポンスオブジェクト。"""
    response = MagicMock()
    response.text = json.dumps(raw)
    candidate = MagicMock()
    candidate.finish_reason = "STOP"
    response.candidates = [candidate]
    return response


def _field_value(value, quote=None, confidence=0.95):
    text_quote = quote if quote is not None else str(value)
    return {
        "value": value,
        "source_ref": {
            "document_id": "doc_p",
            "page": 1,
            "text_quote": text_quote,
            "confidence": confidence,
        },
    }


def _passport_candidate(document_id="doc_p", page=1, confidence=0.95):
    return {
        "document_id": document_id,
        "page": page,
        "confidence": confidence,
        "detection_basis": "顔写真と身分事項欄を確認",
        "mrz_detected": True,
    }


def test_passport_candidate_rejects_non_finite_confidence():
    for confidence in (
        float("nan"), float("inf"), float("-inf"), -0.01, 1.01, True, "invalid",
    ):
        candidates, invalid_count = _normalize_passport_identity_candidates(
            [_passport_candidate(confidence=confidence)],
            _DOCUMENTS,
        )
        assert candidates == []
        assert invalid_count == 1


def test_passport_candidate_rejects_office_document_even_with_page_count():
    candidates, invalid_count = _normalize_passport_identity_candidates(
        [_passport_candidate(document_id="doc_d")],
        [{**_DOCUMENTS[1], "document_kind": "docx", "page_count": 1}],
    )

    assert candidates == []
    assert invalid_count == 1


def test_passport_candidate_rejects_non_integer_page():
    candidates, invalid_count = _normalize_passport_identity_candidates(
        [_passport_candidate(page=1.5)],
        _DOCUMENTS,
    )

    assert candidates == []
    assert invalid_count == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1990-01-02", "1990-01-02"),
        ("1990/1/2", "1990-01-02"),
        ("1990.01.02", "1990-01-02"),
        ("02 JAN 1990", "1990-01-02"),
        ("2-January-1990", "1990-01-02"),
        ("31/12/1990", "1990-12-31"),
        ("12/31/1990", "1990-12-31"),
    ],
)
def test_iso_birth_date_normalizes_unambiguous_four_digit_year_formats(raw, expected):
    assert _iso_birth_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "02 JAN 90",
        "02/01/1990",
        "01/02/1990",
        "31 FEB 1990",
        "1990-02-30",
        "",
    ],
)
def test_iso_birth_date_rejects_ambiguous_or_invalid_formats(raw):
    assert _iso_birth_date(raw) is None


# ---------- build_extraction_prompt (prompt_template) -------------------


class TestBuildPrompt:
    def test_contains_case_id(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)
        assert "case_test01" in prompt

    def test_contains_document_names(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)
        assert "passport.pdf" in prompt
        assert "diploma.pdf" in prompt

    def test_contains_target_status(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)
        assert "engineer_humanities_international" in prompt

    def test_contains_current_date_context(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)
        assert "今日の日付" in prompt

    def test_no_documents_shows_placeholder(self):
        prompt = build_extraction_prompt(_CASE_META, [])
        assert "(なし)" in prompt

    def test_uses_source_ref_dict_contract(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)
        assert "source_ref" in prompt
        assert "document_id|page|text_quote|confidence" not in prompt

    def test_contains_typed_value_contract(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)
        assert "JSON boolean" in prompt
        assert "JSON number" in prompt
        assert "空文字やnullは使わない" in prompt

    def test_scoped_prompt_accepts_new_scope(self):
        prompt = build_scoped_prompt("applicant_identity", _CASE_META, _DOCUMENTS)
        assert "source_ref" in prompt
        assert "applicant_identity" not in prompt
        assert "applicant.birth_date.value" in prompt
        assert "YYYY-MM-DD" in prompt
        assert "source_ref.text_quote" in prompt


# ---------- _build_ocr_context ------------------------------------------


class TestBuildOcrContext:
    def test_basic_context(self):
        ocr_results = _make_ocr_results()
        context = _build_ocr_context(ocr_results)
        assert "doc_p" in context
        assert "page: 1" in context
        assert "TANAKA TARO" in context

    def test_multiple_documents(self):
        results = [
            OcrResult(
                document_id="doc_a",
                pages=[PageResult(page_number=1, text="Page A", words=[])],
            ),
            OcrResult(
                document_id="doc_b",
                pages=[PageResult(page_number=1, text="Page B", words=[])],
            ),
        ]
        context = _build_ocr_context(results)
        assert "doc_a" in context
        assert "doc_b" in context

    def test_empty_results(self):
        context = _build_ocr_context([])
        assert context == ""


# ---------- extract_text_only (Pattern A) --------------------------------


class TestCallGemini:
    def test_invalid_json_log_does_not_include_response_text(self, caplog):
        response = MagicMock()
        response.text = "\x00TANAKA TARO"
        response.candidates = []
        response.usage_metadata = None

        client = MagicMock()
        client.models.generate_content.return_value = response

        try:
            with caplog.at_level("ERROR", logger="extractors.gemini"):
                _call_gemini(client, [], "prompt")
        except ValueError:
            pass
        else:
            raise AssertionError("_call_gemini should fail on unrecoverable JSON")

        assert "TANAKA TARO" not in caplog.text
        assert "Response head" not in caplog.text


class TestExtractTextOnly:
    @patch("extractors.gemini._get_client")
    def test_returns_extraction_result_new_format(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE_NEW
        )
        mock_get_client.return_value = mock_client

        result = extract_text_only(_make_ocr_results(), _CASE_META, _DOCUMENTS)

        assert isinstance(result, ExtractionResult)
        # display_case_data は値のみ
        assert result.display_case_data["applicant"]["name_roman"] == "TANAKA TARO"
        # case_data は FieldValue 構造
        assert result.case_data["applicant"]["name_roman"]["value"] == "TANAKA TARO"
        assert result.review["summary"] == "問題なし"
        # field_metadata が自動生成されている
        assert "applicant.name_roman" in result.field_metadata
        assert result.field_metadata["applicant.name_roman"]["confidence"] == 0.95
        mock_client.models.generate_content.assert_called_once()

    def test_rejects_raw_source_refs_format(self):
        raw = {
            "case_data": {
                "applicant": {
                    "name_roman": {
                        "value": "TANAKA TARO",
                        "source_refs": [
                            {
                                "document_id": "doc_p",
                                "page": 1,
                                "text_quote": "TANAKA TARO",
                                "confidence": 0.95,
                            }
                        ],
                    }
                }
            },
            "review": {},
        }

        try:
            _build_extraction_result(raw)
        except ValueError as exc:
            assert "source_ref" in str(exc)
        else:
            raise AssertionError("raw source_refs response should be rejected")

    def test_build_extraction_result_preserves_typed_values(self):
        raw = {
            "case_data": {
                "applicant": {
                    "family": {
                        "has_accompanying_members": _field_value(False, "同伴者の有無 無"),
                    },
                    "immigration_history": {
                        "has_entries": _field_value(False, "過去の出入国歴 無"),
                        "entries_count": _field_value(0, "回数 0"),
                        "prior_coe_applications": {
                            "has_history": _field_value(True, "申請歴 有"),
                            "count": _field_value(1, "申請回数 1"),
                        },
                    },
                },
                "employer": {
                    "has_corporate_number": _field_value(True, "法人番号 有"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["applicant"]["family"]["has_accompanying_members"] is False
        assert result.display_case_data["applicant"]["immigration_history"]["has_entries"] is False
        assert result.display_case_data["applicant"]["immigration_history"]["entries_count"] == 0
        assert result.display_case_data["applicant"]["immigration_history"]["prior_coe_applications"]["has_history"] is True
        assert result.display_case_data["applicant"]["immigration_history"]["prior_coe_applications"]["count"] == 1
        assert result.display_case_data["employer"]["has_corporate_number"] is True
        assert result.case_data["applicant"]["immigration_history"]["entries_count"]["value"] == 0
        assert result.field_metadata["applicant.immigration_history.entries_count"]["confidence"] == 0.95

    def test_build_extraction_result_allows_typed_default_without_source_ref(self):
        raw = {
            "case_data": {
                "applicant": {
                    "immigration_history": {
                        "has_entries": {
                            "value": False,
                            "source_ref": {
                                "document_id": "",
                                "page": 0,
                                "text_quote": "",
                                "confidence": 0,
                            },
                        },
                        "entries_count": {
                            "value": 0,
                            "source_ref": {
                                "document_id": "",
                                "page": 0,
                                "text_quote": "",
                                "confidence": 0,
                            },
                        },
                    },
                },
            },
            "review": {"findings": ["過去の出入国歴は記載なしのため既定値"]},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["applicant"]["immigration_history"]["has_entries"] is False
        assert result.display_case_data["applicant"]["immigration_history"]["entries_count"] == 0
        assert result.field_metadata["applicant.immigration_history.has_entries"]["source_refs"] == []
        assert result.field_metadata["applicant.immigration_history.entries_count"]["source_refs"] == []

    @patch("extractors.gemini._get_client")
    def test_prompt_contains_ocr_text(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE_NEW
        )
        mock_get_client.return_value = mock_client

        extract_text_only(_make_ocr_results(), _CASE_META)

        call_args = mock_client.models.generate_content.call_args
        # prompt is the last element of contents
        prompt_text = call_args.kwargs.get("contents", call_args[1].get("contents", []))[-1]
        assert "TANAKA TARO" in prompt_text


# ---------- extract_pdf_direct (Pattern B) --------------------------------


class TestExtractPdfDirect:
    @patch("extractors.gemini.types.Part.from_bytes")
    @patch("extractors.gemini._get_client")
    def test_returns_extraction_result(self, mock_get_client, mock_from_bytes):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE_NEW
        )
        mock_get_client.return_value = mock_client
        mock_from_bytes.return_value = "pdf_part"

        pdf_contents = [("doc_p", b"fake_pdf_bytes")]
        result = extract_pdf_direct(pdf_contents, _CASE_META, _DOCUMENTS)

        assert isinstance(result, ExtractionResult)
        assert result.display_case_data["applicant"]["nationality_region"] == "JP"
        mock_from_bytes.assert_called_once_with(
            data=b"fake_pdf_bytes", mime_type="application/pdf"
        )

    @patch("extractors.gemini.types.Part.from_bytes")
    @patch("extractors.gemini._get_client")
    def test_multiple_pdfs(self, mock_get_client, mock_from_bytes):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE_NEW
        )
        mock_get_client.return_value = mock_client
        mock_from_bytes.return_value = "pdf_part"

        pdf_contents = [("doc_p", b"pdf1"), ("doc_d", b"pdf2")]
        extract_pdf_direct(pdf_contents, _CASE_META)

        assert mock_from_bytes.call_count == 2


# ---------- extract_with_images (Pattern C) --------------------------------


class TestExtractWithImages:
    @patch("extractors.gemini.types.Part.from_bytes")
    @patch("extractors.gemini._get_client")
    def test_returns_extraction_result(self, mock_get_client, mock_from_bytes):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE_NEW
        )
        mock_get_client.return_value = mock_client
        mock_from_bytes.return_value = "img_part"

        # PNG magic bytes
        png_bytes = b"\x89PNG" + b"\x00" * 100
        result = extract_with_images(
            _make_ocr_results(), [("doc_p", png_bytes)], _CASE_META
        )

        assert isinstance(result, ExtractionResult)
        mock_from_bytes.assert_called_once_with(data=png_bytes, mime_type="image/png")

    @patch("extractors.gemini.types.Part.from_bytes")
    @patch("extractors.gemini._get_client")
    def test_jpeg_detection(self, mock_get_client, mock_from_bytes):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE_NEW
        )
        mock_get_client.return_value = mock_client
        mock_from_bytes.return_value = "img_part"

        jpg_bytes = b"\xff\xd8\xff" + b"\x00" * 100
        extract_with_images(
            _make_ocr_results(), [("doc_p", jpg_bytes)], _CASE_META
        )

        mock_from_bytes.assert_called_once_with(data=jpg_bytes, mime_type="image/jpeg")


# ---------- extract_all_scopes ------------------------------------------


class TestExtractAllScopes:
    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_merges_scope_results_deeply(self, mock_extract_scoped, mock_call_gemini):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": _field_value("1990-01-02"),
                        }
                    },
                    "passport_identity_page_candidates": [_passport_candidate()],
                }
            if scope == "education":
                return {"case_data": {"applicant": {"education": [{"school_name": _field_value("ABC University")}]}}}
            if scope == "employer":
                return {"case_data": {"employer": {"name": _field_value("Example Inc.")}}}
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {"missing_items": []}

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["name_roman"] == "TANAKA TARO"
        assert result.display_case_data["applicant"]["birth_date"] == "1990-01-02"
        assert result.display_case_data["applicant"]["education"][0]["school_name"] == "ABC University"
        assert result.display_case_data["employer"]["name"] == "Example Inc."
        assert "passport_identity_page_candidates" not in result.display_case_data
        assert result.review["passport_identity_authority"] == {
            "status": "verified",
            "required_action": "none",
            "candidates": [{"document_id": "doc_p", "page": 1}],
            "verified_fields": ["applicant.name_roman", "applicant.birth_date"],
            "blocked_fields": [],
        }

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_normalizes_passport_english_month_birth_date_and_builds_8_digit_row(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": _field_value("02 JAN 1990", "02 JAN 1990"),
                        }
                    },
                    "passport_identity_page_candidates": [_passport_candidate()],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["birth_date"] == "1990-01-02"
        birth_ref = result.field_metadata["applicant.birth_date"]["source_refs"][0]
        assert birth_ref["text_quote"] == "02 JAN 1990"
        for path in ("applicant.name_roman", "applicant.birth_date"):
            result.field_metadata[path]["source_refs"][0]["anchor"] = {
                "status": "resolved",
                "type": "pdf_bbox",
                "resolver_type": "pdf_text_layer",
                "page": 1,
            }

        mapping = {
            "schema_version": "test",
            "mappings": [{
                "canonical_id": "applicant.birth_date",
                "value_path": "applicant.birth_date",
                "field_id": "birth",
                "field_name": "",
                "input_type": "text",
                "transform": "date_yyyymmdd",
            }],
        }
        form_definitions = {
            "fields": [{
                "section": "identity",
                "no": "2",
                "label": "生年月日",
                "required": True,
                "controls": [{
                    "field_id": "birth", "field_name": "", "input_type": "text",
                }],
            }],
        }
        application_data = build_application_data(
            {
                "case_id": "case_test01",
                "workflow_state": "extracted",
                "case_data": result.display_case_data,
                "review": result.review,
                "field_metadata": result.field_metadata,
            },
            mapping,
            form_definitions,
        )

        assert application_data["rows"][0]["fill_value"] == "19900102"

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_withholds_ambiguous_passport_birth_date_instead_of_guessing(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": _field_value("02/01/1990", "02/01/1990"),
                        }
                    },
                    "passport_identity_page_candidates": [_passport_candidate()],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["birth_date"] == ""
        birth_meta = result.field_metadata["applicant.birth_date"]
        assert birth_meta["alternatives"][0]["value"] == "02/01/1990"
        assert birth_meta["alternatives"][0]["source_refs"][0]["text_quote"] == "02/01/1990"
        authority = result.review["passport_identity_authority"]
        assert authority["status"] == "blocked"
        assert authority["blocked_fields"] == ["applicant.birth_date"]
        assert any("YYYY-MM-DD" in error for error in result.review["validation_errors"])

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_withholds_name_and_birth_date_when_passport_candidate_is_missing(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": _field_value("1990-01-02"),
                        }
                    },
                    "passport_identity_page_candidates": [],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["name_roman"] == ""
        assert result.display_case_data["applicant"]["birth_date"] == ""
        name_meta = result.field_metadata["applicant.name_roman"]
        birth_meta = result.field_metadata["applicant.birth_date"]
        assert name_meta["source_refs"] == []
        assert name_meta["alternatives"][0]["value"] == "TANAKA TARO"
        assert name_meta["alternatives"][0]["source_refs"][0]["document_id"] == "doc_p"
        assert birth_meta["alternatives"][0]["value"] == "1990-01-02"
        assert any("候補なし" in error for error in result.review["validation_errors"])
        assert any("自動確定せず" in finding for finding in result.review["findings"])
        assert result.review["expected_route"] == "needs_review"
        assert result.review["passport_identity_authority"]["status"] == "blocked"
        assert result.review["passport_identity_authority"]["required_action"] == "human_required"

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_withholds_both_fields_when_passport_candidates_are_ambiguous(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        documents = [
            _DOCUMENTS[0],
            {
                "file_name": "old_passport.pdf",
                "document_role": "passport",
                "document_id": "doc_old",
                "document_kind": "pdf",
                "page_count": 1,
            },
        ]

        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": _field_value("1990-01-02"),
                        }
                    },
                    "passport_identity_page_candidates": [
                        _passport_candidate(),
                        _passport_candidate("doc_old", 1),
                    ],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, documents)

        assert result.display_case_data["applicant"]["name_roman"] == ""
        assert result.display_case_data["applicant"]["birth_date"] == ""
        assert any("候補が複数" in error for error in result.review["validation_errors"])

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_withholds_only_field_whose_source_mismatches_unique_passport_page(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                mismatched_birth = _field_value("1990-01-02")
                mismatched_birth["source_ref"]["page"] = 2
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": mismatched_birth,
                        }
                    },
                    "passport_identity_page_candidates": [_passport_candidate()],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["name_roman"] == "TANAKA TARO"
        assert result.display_case_data["applicant"]["birth_date"] == ""
        assert result.field_metadata["applicant.birth_date"]["alternatives"][0]["value"] == "1990-01-02"
        assert any("生年月日" in error and "一致しません" in error for error in result.review["validation_errors"])

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_rejects_candidate_outside_manifest_page_count(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        documents = [{**_DOCUMENTS[0], "page_count": 1}]

        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": _field_value("1990-01-02"),
                        }
                    },
                    "passport_identity_page_candidates": [_passport_candidate(page=2)],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, documents)

        assert result.display_case_data["applicant"]["name_roman"] == ""
        assert any("実ページ範囲外" in error for error in result.review["validation_errors"])

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_withholds_unique_low_confidence_candidate(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value("TANAKA TARO"),
                            "birth_date": _field_value("1990-01-02"),
                        }
                    },
                    "passport_identity_page_candidates": [
                        _passport_candidate(confidence=0.79)
                    ],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["name_roman"] == ""
        assert any("確信度が低い" in error for error in result.review["validation_errors"])

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_withholds_name_when_source_quote_is_mrz_not_visual_zone(
        self, mock_extract_scoped, mock_call_gemini,
    ):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                return {
                    "case_data": {
                        "applicant": {
                            "name_roman": _field_value(
                                "TANAKA TARO", "P<JPN TANAKA<<TARO"
                            ),
                            "birth_date": _field_value("1990-01-02"),
                        }
                    },
                    "passport_identity_page_candidates": [_passport_candidate()],
                }
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [], "validation_errors": [], "findings": [],
        }

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["name_roman"] == ""
        assert result.display_case_data["applicant"]["birth_date"] == "1990-01-02"
        authority = result.review["passport_identity_authority"]
        assert authority["status"] == "blocked"
        assert authority["verified_fields"] == ["applicant.birth_date"]
        assert authority["blocked_fields"] == ["applicant.name_roman"]
        assert any("MRZ形式" in error for error in result.review["validation_errors"])

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_partial_scope_failure_returns_reviewable_result(self, mock_extract_scoped, mock_call_gemini):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                raise TimeoutError("read operation timed out")
            if scope == "employer":
                return {"case_data": {"employer": {"name": _field_value("Example Inc.")}}}
            if scope == "education":
                return {"case_data": {"applicant": {"education": [{"school_name": _field_value("ABC University")}]}}}
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {"missing_items": [], "validation_errors": [], "findings": []}

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["employer"]["name"] == "Example Inc."
        assert result.display_case_data["applicant"]["education"][0]["school_name"] == "ABC University"
        assert any("applicant_identity" in error for error in result.review["validation_errors"])

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_runs_new_extraction_scopes(self, mock_extract_scoped, mock_call_gemini):
        mock_extract_scoped.return_value = {
            "case_data": {"applicant": {"name_roman": _field_value("TANAKA TARO")}}
        }
        mock_call_gemini.return_value = {"missing_items": [], "validation_errors": [], "findings": []}

        extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        called_scopes = [call.args[0] for call in mock_extract_scoped.call_args_list]
        assert set(called_scopes) == set(EXTRACTION_SCOPES)

    @patch("extractors.gemini.extract_scoped")
    def test_raises_when_all_required_scopes_fail(self, mock_extract_scoped):
        mock_extract_scoped.side_effect = TimeoutError("read operation timed out")

        try:
            extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)
        except RuntimeError as exc:
            assert "All extraction scopes failed" in str(exc)
        else:
            raise AssertionError("extract_all_scopes should fail when all scopes fail")

    @patch("extractors.gemini.extract_scoped")
    def test_preserves_leaked_api_key_error_when_all_scopes_fail(self, mock_extract_scoped):
        mock_extract_scoped.side_effect = RuntimeError(
            "403 PERMISSION_DENIED. Your API key was reported as leaked. Please use another API key."
        )

        try:
            extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)
        except RuntimeError as exc:
            assert "Gemini API key was reported as leaked" in str(exc)
            assert "Replace GOOGLE_API_KEY" in str(exc)
        else:
            raise AssertionError("extract_all_scopes should fail when all scopes fail")


# ---------- _extract_field_metadata ------------------------------------


class TestExtractFieldMetadata:
    def test_extracts_from_new_format(self):
        case_data = {
            "applicant": {
                "name_roman": {
                    "value": "YAMADA TARO",
                    "source_refs": [
                        {"document_id": "doc_p", "page": 1, "text_quote": "YAMADA TARO", "confidence": 0.95}
                    ],
                },
                "nationality_region": {
                    "value": "JP",
                    "source_refs": [
                        {"document_id": "doc_p", "page": 1, "text_quote": "JP", "confidence": 0.9}
                    ],
                },
            }
        }
        result = _extract_field_metadata(case_data)
        assert "applicant.name_roman" in result
        assert result["applicant.name_roman"]["confidence"] == 0.95
        assert "applicant.nationality_region" in result

    def test_handles_list_fields(self):
        case_data = {
            "applicant": {
                "education": [
                    {
                        "school_name": {
                            "value": "東京大学",
                            "source_refs": [{"confidence": 0.9}],
                        }
                    }
                ]
            }
        }
        result = _extract_field_metadata(case_data)
        assert "applicant.education.0.school_name" in result

    def test_empty_source_refs(self):
        case_data = {
            "applicant": {
                "name": {"value": "", "source_refs": []},
            }
        }
        result = _extract_field_metadata(case_data)
        assert result["applicant.name"]["confidence"] is None

    def test_carries_alternatives(self):
        case_data = {
            "employment": {
                "monthly_salary": {
                    "value": "250000",
                    "source_refs": [
                        {"document_id": "doc_offer", "page": 1, "text_quote": "250000", "confidence": 0.9}
                    ],
                    "alternatives": [
                        {
                            "value": "230000",
                            "source_refs": [
                                {"document_id": "doc_resume", "page": 2, "text_quote": "230000", "confidence": 0.8}
                            ],
                        }
                    ],
                },
            }
        }

        result = _extract_field_metadata(case_data)

        assert result["employment.monthly_salary"]["alternatives"] == [
            {
                "value": "230000",
                "source_refs": [
                    {"document_id": "doc_resume", "page": 2, "text_quote": "230000", "confidence": 0.8}
                ],
            }
        ]


class TestUnflattenFieldValues:
    def test_accepts_source_ref_dict(self):
        raw = {
            "value": "TANAKA TARO",
            "source_ref": {
                "document_id": "doc_p",
                "page": "1",
                "text_quote": "TANAKA TARO",
                "confidence": "0.95",
            },
        }
        result = _unflatten_field_values(raw)
        assert result == {
            "value": "TANAKA TARO",
            "source_refs": [
                {
                    "document_id": "doc_p",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.95,
                }
            ],
        }

    def test_drops_empty_source_ref(self):
        raw = {
            "value": "",
            "source_ref": {
                "document_id": "",
                "page": 0,
                "text_quote": "",
                "confidence": 0,
            },
        }
        result = _unflatten_field_values(raw)
        assert result == {"value": "", "source_refs": []}

    def test_normalizes_alternatives(self):
        raw = {
            "value": "250000",
            "source_ref": {
                "document_id": "doc_offer",
                "page": 1,
                "text_quote": "Monthly salary 250000",
                "confidence": 0.95,
            },
            "alternatives": [
                {
                    "value": "230000",
                    "source_ref": {
                        "document_id": "doc_resume",
                        "page": "2",
                        "text_quote": "Salary 230000",
                        "confidence": "0.82",
                    },
                }
            ],
        }

        result = _unflatten_field_values(raw)

        assert result["alternatives"] == [
            {
                "value": "230000",
                "source_refs": [
                    {
                        "document_id": "doc_resume",
                        "page": 2,
                        "text_quote": "Salary 230000",
                        "confidence": 0.82,
                    }
                ],
            }
        ]

    def test_filters_alternative_quality(self):
        raw = {
            "value": "abc",
            "source_ref": {
                "document_id": "doc_primary",
                "page": 1,
                "text_quote": "abc",
                "confidence": 0.9,
            },
            "alternatives": [
                {
                    "value": "ＡＢＣ ",
                    "source_ref": {
                        "document_id": "doc_same",
                        "page": 1,
                        "text_quote": "ABC",
                        "confidence": 0.8,
                    },
                },
                {
                    "value": "",
                    "source_ref": {
                        "document_id": "doc_empty",
                        "page": 1,
                        "text_quote": "empty",
                        "confidence": 0.8,
                    },
                },
                {
                    "value": "different",
                    "source_ref": {
                        "document_id": "doc_no_quote",
                        "page": 1,
                        "text_quote": "",
                        "confidence": 0.8,
                    },
                },
                {
                    "value": "first",
                    "source_ref": {
                        "document_id": "doc_first",
                        "page": 1,
                        "text_quote": "first",
                        "confidence": 0.8,
                    },
                },
            ],
        }

        result = _unflatten_field_values(raw)

        assert result["alternatives"] == [
            {
                "value": "first",
                "source_refs": [
                    {
                        "document_id": "doc_first",
                        "page": 1,
                        "text_quote": "first",
                        "confidence": 0.8,
                    }
                ],
            }
        ]

    def test_caps_alternatives_at_two(self):
        raw = {
            "value": "primary",
            "source_ref": {
                "document_id": "doc_primary",
                "page": 1,
                "text_quote": "primary",
                "confidence": 0.9,
            },
            "alternatives": [
                {
                    "value": f"alt-{index}",
                    "source_ref": {
                        "document_id": f"doc_{index}",
                        "page": 1,
                        "text_quote": f"alt-{index}",
                        "confidence": 0.8,
                    },
                }
                for index in range(3)
            ],
        }

        result = _unflatten_field_values(raw)

        assert [alt["value"] for alt in result["alternatives"]] == ["alt-0", "alt-1"]

    def test_raw_source_refs_guard_allows_alternative_source_ref(self):
        raw = {
            "value": "250000",
            "source_ref": {
                "document_id": "doc_offer",
                "page": 1,
                "text_quote": "250000",
                "confidence": 0.9,
            },
            "alternatives": [
                {
                    "value": "230000",
                    "source_ref": {
                        "document_id": "doc_resume",
                        "page": 1,
                        "text_quote": "230000",
                        "confidence": 0.8,
                    },
                }
            ],
        }

        assert _uses_raw_source_refs(raw) is False

    def test_raw_source_refs_guard_rejects_alternative_source_refs(self):
        raw = {
            "value": "250000",
            "source_ref": {
                "document_id": "doc_offer",
                "page": 1,
                "text_quote": "250000",
                "confidence": 0.9,
            },
            "alternatives": [
                {
                    "value": "230000",
                    "source_refs": [
                        {
                            "document_id": "doc_resume",
                            "page": 1,
                            "text_quote": "230000",
                            "confidence": 0.8,
                        }
                    ],
                }
            ],
        }

        assert _uses_raw_source_refs(raw) is True

# ---------- _extract_display_values ------------------------------------


class TestExtractDisplayValues:
    def test_unwraps_values(self):
        case_data = {
            "applicant": {
                "name_roman": {
                    "value": "YAMADA TARO",
                    "source_refs": [{"confidence": 0.95}],
                    "alternatives": [
                        {
                            "value": "YAMADA JIRO",
                            "source_refs": [{"confidence": 0.7}],
                        }
                    ],
                },
            }
        }
        result = _extract_display_values(case_data)
        assert result == {"applicant": {"name_roman": "YAMADA TARO"}}

    def test_handles_lists(self):
        case_data = {
            "education": [
                {
                    "school_name": {"value": "東京大学", "source_refs": []},
                }
            ]
        }
        result = _extract_display_values(case_data)
        assert result["education"][0]["school_name"] == "東京大学"


# ---------- _map_field_metadata -----------------------------------------


class TestMapFieldMetadata:
    def test_dict_passthrough(self):
        raw_metadata = {
            "applicant.name_roman": {
                "source_refs": [
                    {
                        "document_id": "doc_p",
                        "page": 1,
                        "text_quote": "TANAKA",
                        "confidence": 0.95,
                    }
                ]
            }
        }
        result = _map_field_metadata(raw_metadata)
        assert "applicant.name_roman" in result

    def test_list_to_dict_conversion(self):
        raw_metadata = [
            {
                "field_path": "applicant.name_roman",
                "source_refs": [
                    {"text_quote": "TANAKA", "confidence": 0.95}
                ],
            }
        ]
        result = _map_field_metadata(raw_metadata)
        assert "applicant.name_roman" in result
        assert result["applicant.name_roman"]["source_refs"][0]["text_quote"] == "TANAKA"
