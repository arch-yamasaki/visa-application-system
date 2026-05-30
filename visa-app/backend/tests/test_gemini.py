"""extractors.gemini のユニットテスト。Gemini API はモックで置き換え。"""

import json
from unittest.mock import MagicMock, patch

from extractors.gemini import (
    _build_ocr_context,
    _call_gemini,
    _extract_field_metadata,
    _extract_display_values,
    _unflatten_field_values,
    _map_field_metadata,
    EXTRACTION_SCOPES,
    extract_all_scopes,
    extract_pdf_direct,
    extract_text_only,
    extract_with_images,
)
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

# 旧形式（field_metadata 別出し）の Gemini レスポンス
_GEMINI_RESPONSE_OLD = {
    "case_data": {
        "applicant": {"name_roman": "TANAKA TARO", "nationality_region": "JP"},
    },
    "review": {
        "missing_items": [],
        "summary": "問題なし",
    },
    "field_metadata": {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_p",
                    "page": "1",
                    "text_quote": "TANAKA TARO",
                    "confidence": "0.95",
                }
            ]
        }
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

    def test_scoped_prompt_accepts_new_scope(self):
        prompt = build_scoped_prompt("applicant_identity", _CASE_META, _DOCUMENTS)
        assert "source_ref" in prompt
        assert "applicant_identity" not in prompt


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

    @patch("extractors.gemini._get_client")
    def test_returns_extraction_result_old_format(self, mock_get_client):
        """旧形式のレスポンスでも動作する（互換性テスト）。"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE_OLD
        )
        mock_get_client.return_value = mock_client

        result = extract_text_only(_make_ocr_results(), _CASE_META, _DOCUMENTS)

        assert isinstance(result, ExtractionResult)
        assert result.case_data["applicant"]["name_roman"] == "TANAKA TARO"
        assert result.display_case_data["applicant"]["name_roman"] == "TANAKA TARO"
        assert result.review["summary"] == "問題なし"
        mock_client.models.generate_content.assert_called_once()

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
                return {"case_data": {"applicant": {"name_roman": "TANAKA TARO"}}}
            if scope == "education":
                return {"case_data": {"applicant": {"education": [{"school_name": "ABC University"}]}}}
            if scope == "employer":
                return {"case_data": {"employer": {"name": "Example Inc."}}}
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {"missing_items": []}

        result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert result.display_case_data["applicant"]["name_roman"] == "TANAKA TARO"
        assert result.display_case_data["applicant"]["education"][0]["school_name"] == "ABC University"
        assert result.display_case_data["employer"]["name"] == "Example Inc."

    @patch("extractors.gemini._call_gemini")
    @patch("extractors.gemini.extract_scoped")
    def test_partial_scope_failure_returns_reviewable_result(self, mock_extract_scoped, mock_call_gemini):
        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                raise TimeoutError("read operation timed out")
            if scope == "employer":
                return {"case_data": {"employer": {"name": "Example Inc."}}}
            if scope == "education":
                return {"case_data": {"applicant": {"education": [{"school_name": "ABC University"}]}}}
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
        mock_extract_scoped.return_value = {"case_data": {}}
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

    def test_keeps_legacy_source_string(self):
        raw = {"value": "TANAKA TARO", "source": "doc_p|1|TANAKA TARO|0.95"}
        result = _unflatten_field_values(raw)
        assert result["source_refs"][0]["document_id"] == "doc_p"


# ---------- _extract_display_values ------------------------------------


class TestExtractDisplayValues:
    def test_unwraps_values(self):
        case_data = {
            "applicant": {
                "name_roman": {
                    "value": "YAMADA TARO",
                    "source_refs": [{"confidence": 0.95}],
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
