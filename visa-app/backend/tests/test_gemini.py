"""extractors.gemini のユニットテスト。Gemini API はモックで置き換え。"""

import json
from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors as genai_errors

from extractors.gemini import (
    DEFAULT_GEMINI_MODEL,
    GEMINI_RETRYABLE_STATUS_CODES,
    MODEL_NAME,
    _build_ocr_context,
    _attach_source_locations,
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


def _assert_sampling_parameters_omitted(config):
    config_values = config.model_dump(exclude_none=True)
    for parameter in ("temperature", "top_p", "top_k"):
        assert parameter not in config_values


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


def _field_value_without_ref(value):
    return {
        "value": value,
        "source_ref": {
            "document_id": "",
            "page": 0,
            "text_quote": "",
            "confidence": 0,
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
        assert "12桁" in prompt
        assert "完全な日付" in prompt
        assert "applicant.occupation" in prompt
        assert "employment.job_category_primary" in prompt

    def test_legacy_prompt_includes_rasens_job_category_options_once(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)

        assert prompt.count("## RASENS選択肢") == 1
        assert "根拠資料から予定業務を分類できる場合だけ" in prompt
        assert "分類できない場合は既存契約どおりvalueを空文字" in prompt
        assert "日本語部分だけの出力は禁止" in prompt
        assert "ラベル全体を一字一句そのまま" in prompt
        assert "建築・土木・測量技術 Architecture, civil engineering, surveying techniques" in prompt
        assert "情報処理・通信技術 Information processing, communications technology" in prompt

    def test_legacy_prompt_separates_identity_authority_rules(self):
        prompt = build_extraction_prompt(_CASE_META, _DOCUMENTS)

        assert "現在の職業・身分として明記された値だけを使うこと" in prompt
        assert "Occupation、Profession、Job title等の欄があればその値を優先" in prompt
        assert "学位、資格、採用後の予定業務、職種区分から推測せず" in prompt
        assert "旅券や身分事項書類の出生地欄を優先" in prompt
        assert "その欄に書かれた表記をそのまま使うこと" in prompt
        assert "別欄の国名追加は禁止" in prompt
        assert "本国住所・現住所・会社所在地を代用せず" in prompt
        assert "本国の現住所・居住地として明記された値を優先" in prompt

    def test_scoped_prompt_accepts_new_scope(self):
        prompt = build_scoped_prompt("applicant_identity", _CASE_META, _DOCUMENTS)
        assert "source_ref" in prompt
        assert "applicant_identity" not in prompt
        assert "applicant.birth_date.value" in prompt
        assert "YYYY-MM-DD" in prompt
        assert "source_ref.text_quote" in prompt
        assert "内部契約で指定したfield" in prompt

    def test_scoped_prompt_separates_current_occupation_from_planned_job_category(self):
        identity_prompt = build_scoped_prompt("applicant_identity", _CASE_META, _DOCUMENTS)
        employment_prompt = build_scoped_prompt("employment", _CASE_META, _DOCUMENTS)

        assert "申請人の現在の職業・身分" in identity_prompt
        assert "現在の職業・身分として明記された値だけを使い" in identity_prompt
        assert "学位、資格、採用後の予定業務、職種区分から推測しない" in identity_prompt
        assert "予定業務の職種区分" in employment_prompt
        assert "position_title" in employment_prompt

    def test_scoped_prompt_separates_birth_place_from_home_country_address(self):
        prompt = build_scoped_prompt("applicant_identity", _CASE_META, _DOCUMENTS)

        assert "出生地欄を優先" in prompt
        assert "その欄に書かれた表記をそのまま使ってください" in prompt
        assert "別欄の国名追加は禁止" in prompt
        assert "本国住所・現住所・会社所在地を代用しない" in prompt
        assert "本国の現住所・居住地として明記された値を優先" in prompt
        assert "出生地を代用しない" in prompt

    def test_employment_prompt_includes_rasens_job_category_options(self):
        prompt = build_scoped_prompt("employment", _CASE_META, _DOCUMENTS)

        assert "## RASENS選択肢" in prompt
        assert "根拠資料から予定業務を分類できる場合だけ" in prompt
        assert "分類できない場合は既存契約どおりvalueを空文字" in prompt
        assert "日本語部分だけの出力は禁止" in prompt
        assert "内定後の職務内容・役職・配属業務を根拠に分類" in prompt
        assert "建築・土木・測量技術 Architecture, civil engineering, surveying techniques" in prompt
        assert "情報処理・通信技術 Information processing, communications technology" in prompt
        assert "- 選択してください" not in prompt

    def test_job_category_options_are_only_in_employment_prompt(self):
        prompt = build_scoped_prompt("applicant_identity", _CASE_META, _DOCUMENTS)

        assert "## RASENS選択肢" not in prompt

    def test_employment_history_prompt_keeps_month_precision(self):
        prompt = build_scoped_prompt("employment_history", _CASE_META, _DOCUMENTS)

        assert "年月まで分かる場合は `YYYY-MM`" in prompt
        assert "日まで明記されていない場合に `-01` 等の日付を補完しない" in prompt


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
    def test_default_model_is_gemini_37_flash(self):
        assert DEFAULT_GEMINI_MODEL == "gemini-3.7-flash"
        assert GEMINI_RETRYABLE_STATUS_CODES == frozenset({429, 500, 502, 503, 504})

    def test_omits_sampling_parameters(self):
        client = MagicMock()
        client.models.generate_content.return_value = _mock_gemini_response({})

        _call_gemini(client, [], "prompt")

        call = client.models.generate_content.call_args
        assert call.kwargs["model"] == MODEL_NAME
        _assert_sampling_parameters_omitted(call.kwargs["config"])

    def test_uses_response_json_schema(self):
        client = MagicMock()
        client.models.generate_content.return_value = _mock_gemini_response({})

        _call_gemini(client, [], "prompt")

        config = client.models.generate_content.call_args.kwargs["config"]
        assert config.response_json_schema["type"] == "object"
        assert config.response_schema is None

    @patch("extractors.gemini.time.sleep")
    def test_retries_retryable_error_until_success(self, mock_sleep):
        client = MagicMock()
        client.models.generate_content.side_effect = [
            genai_errors.ServerError(
                503,
                {"error": {"status": "UNAVAILABLE", "message": "temporary body"}},
            ),
            _mock_gemini_response({}),
        ]

        result = _call_gemini(client, [], "prompt")

        assert result == {}
        assert client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("extractors.gemini.time.sleep")
    def test_retries_429_until_success(self, mock_sleep):
        client = MagicMock()
        client.models.generate_content.side_effect = [
            genai_errors.ClientError(
                429,
                {"error": {"status": "RESOURCE_EXHAUSTED", "message": "rate limited"}},
            ),
            _mock_gemini_response({}),
        ]

        result = _call_gemini(client, [], "prompt")

        assert result == {}
        assert client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @pytest.mark.parametrize("error", [TimeoutError(), ConnectionError()])
    @patch("extractors.gemini.time.sleep")
    def test_retries_transport_errors(self, mock_sleep, error):
        client = MagicMock()
        client.models.generate_content.side_effect = [
            error,
            _mock_gemini_response({}),
        ]

        result = _call_gemini(client, [], "prompt")

        assert result == {}
        assert client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("extractors.gemini.time.sleep")
    def test_retryable_error_stops_after_three_attempts(self, mock_sleep):
        client = MagicMock()
        client.models.generate_content.side_effect = genai_errors.ServerError(
            503,
            {"error": {"status": "UNAVAILABLE", "message": "temporary body"}},
        )

        with pytest.raises(genai_errors.ServerError):
            _call_gemini(client, [], "prompt")

        assert client.models.generate_content.call_count == 3
        assert [call.args[0] for call in mock_sleep.call_args_list] == [1.0, 2.0]

    @patch("extractors.gemini.time.sleep")
    def test_non_retryable_error_raises_without_retry(self, mock_sleep):
        client = MagicMock()
        client.models.generate_content.side_effect = genai_errors.ClientError(
            403,
            {"error": {"status": "PERMISSION_DENIED", "message": "do not log body"}},
        )

        with pytest.raises(genai_errors.ClientError):
            _call_gemini(client, [], "prompt")

        assert client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()

    @patch("extractors.gemini.time.sleep")
    def test_retry_logs_do_not_include_error_body(self, mock_sleep, caplog):
        client = MagicMock()
        client.models.generate_content.side_effect = [
            genai_errors.ServerError(
                503,
                {"error": {"status": "UNAVAILABLE", "message": "SECRET BODY"}},
            ),
            _mock_gemini_response({}),
        ]

        with caplog.at_level("WARNING", logger="extractors.gemini"):
            _call_gemini(client, [], "prompt")

        assert "SECRET BODY" not in caplog.text
        assert "attempt" in caplog.text
        assert "ServerError" in caplog.text
        assert "503" in caplog.text
        assert "scope" in caplog.text
        assert "elapsed_ms" in caplog.text

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
        assert client.models.generate_content.call_count == 1


class TestAttachSourceLocations:
    def test_attaches_primary_alternative_and_array_locations(self):
        case_data = {
            "applicant": {
                "name_roman": {
                    "value": "PRIMARY",
                    "source_ref": {"document_id": "doc_pdf"},
                    "alternatives": [
                        {
                            "value": "ALTERNATIVE",
                            "source_ref": {"document_id": "doc_xlsx"},
                        }
                    ],
                },
                "education": [
                    {
                        "school_name": {
                            "value": "SCHOOL",
                            "source_ref": {"document_id": "doc_docx"},
                        }
                    }
                ],
            }
        }
        source_locations = [
            {
                "field_path": "applicant.name_roman",
                "alternative_index": -1,
                "type": "pdf_bbox",
                "page": 1,
                "bbox": {"y_min": 10, "x_min": 20, "y_max": 30, "x_max": 40},
            },
            {
                "field_path": "applicant.name_roman",
                "alternative_index": 0,
                "type": "xlsx_cell",
                "anchor_id": "Sheet1!B2",
            },
            {
                "field_path": "applicant.education.0.school_name",
                "alternative_index": -1,
                "type": "docx_block",
                "anchor_id": "p-0",
            },
        ]

        _attach_source_locations(case_data, source_locations)

        name = case_data["applicant"]["name_roman"]
        school = case_data["applicant"]["education"][0]["school_name"]
        assert name["source_ref"]["locations"] == [
            {
                "type": "pdf_bbox",
                "page": 1,
                "bbox": {"y_min": 10, "x_min": 20, "y_max": 30, "x_max": 40},
            }
        ]
        assert name["alternatives"][0]["source_ref"]["locations"] == [
            {"type": "xlsx_cell", "anchor_id": "Sheet1!B2"}
        ]
        assert school["source_ref"]["locations"] == [
            {"type": "docx_block", "anchor_id": "p-0"}
        ]

    def test_ignores_unknown_path_and_initializes_empty_locations(self):
        case_data = {"applicant": {"name_roman": _field_value("VALUE")}}

        _attach_source_locations(
            case_data,
            [
                {
                    "field_path": "applicant.unknown",
                    "alternative_index": -1,
                    "type": "xlsx_cell",
                    "anchor_id": "Sheet1!A1",
                }
            ],
        )

        assert case_data["applicant"]["name_roman"]["source_ref"]["locations"] == []

    def test_keeps_locations_already_attached_by_a_scope(self):
        field_value = _field_value("VALUE")
        field_value["source_ref"]["locations"] = [
            {"type": "xlsx_cell", "anchor_id": "Sheet1!B2"}
        ]
        case_data = {"applicant": {"name_roman": field_value}}

        _attach_source_locations(case_data, [])

        assert field_value["source_ref"]["locations"] == [
            {"type": "xlsx_cell", "anchor_id": "Sheet1!B2"}
        ]

    def test_build_result_merges_top_level_locations_without_leaking_them(self):
        parsed = {
            "case_data": {
                "applicant": {"name_roman": _field_value("VALUE")},
            },
            "review": {},
            "source_locations": [
                {
                    "field_path": "applicant.name_roman",
                    "alternative_index": -1,
                    "type": "xlsx_cell",
                    "anchor_id": "Sheet1!B2",
                }
            ],
        }

        result = _build_extraction_result(parsed)

        assert result.field_metadata["applicant.name_roman"]["source_refs"][0]["locations"] == [
            {"type": "xlsx_cell", "anchor_id": "Sheet1!B2"}
        ]
        assert "source_locations" not in result.case_data


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
        assert result.field_metadata["applicant.name_roman"]["has_value"] is True
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

    def test_build_extraction_result_normalizes_internal_identity_values_with_sources(self):
        raw = {
            "case_data": {
                "applicant": {
                    "sex": _field_value("男 Male", "男 Male"),
                    "marital_status": _field_value("無 Single", "無 Single"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["applicant"]["sex"] == "male"
        assert result.display_case_data["applicant"]["marital_status"] == "single"
        assert result.field_metadata["applicant.sex"]["source_refs"][0]["text_quote"] == "男 Male"
        assert result.field_metadata["applicant.marital_status"]["source_refs"][0]["text_quote"] == "無 Single"

    def test_build_extraction_result_accepts_only_thirteen_digit_corporate_number(self):
        raw = {
            "case_data": {
                "employer": {
                    "has_corporate_number": _field_value(False, "法人番号"),
                    "corporate_number": _field_value("123-4567 8901 23", "123-4567 8901 23"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employer"]["corporate_number"] == "1234567890123"
        assert result.display_case_data["employer"]["has_corporate_number"] is True
        assert result.field_metadata["employer.corporate_number"]["source_refs"][0]["text_quote"] == "123-4567 8901 23"
        has_corporate_number_meta = result.field_metadata["employer.has_corporate_number"]
        assert has_corporate_number_meta["origin"] == "derived"
        assert has_corporate_number_meta["source_refs"] == []
        assert "alternatives" not in has_corporate_number_meta

    def test_build_extraction_result_withholds_twelve_digit_corporate_number(self):
        raw = {
            "case_data": {
                "employer": {
                    "has_corporate_number": _field_value(True, "法人番号"),
                    "corporate_number": _field_value("123-4567 8901 2", "123-4567 8901 2"),
                },
            },
            "review": {"validation_errors": [], "missing_items": [], "findings": []},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employer"]["corporate_number"] == ""
        assert result.display_case_data["employer"]["has_corporate_number"] is False
        corporate_meta = result.field_metadata["employer.corporate_number"]
        has_corporate_number_meta = result.field_metadata["employer.has_corporate_number"]
        assert corporate_meta["origin"] == "derived"
        assert corporate_meta["source_refs"] == []
        assert "alternatives" not in corporate_meta
        assert has_corporate_number_meta["origin"] == "derived"
        assert has_corporate_number_meta["source_refs"] == []
        assert "alternatives" not in has_corporate_number_meta
        assert result.review["expected_route"] == "needs_review"
        assert any("13桁" in error for error in result.review["validation_errors"])

    def test_build_extraction_result_normalizes_full_joining_date(self):
        raw = {
            "case_data": {
                "employment": {
                    "joining_date": _field_value("2026/4/5", "2026/4/5"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["joining_date"] == "2026-04-05"
        assert result.field_metadata["employment.joining_date"]["source_refs"][0]["text_quote"] == "2026/4/5"

    def test_build_extraction_result_withholds_month_only_joining_date(self):
        raw = {
            "case_data": {
                "employment": {
                    "joining_date": _field_value("2026-04", "2026-04"),
                },
            },
            "review": {"validation_errors": [], "missing_items": [], "findings": []},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["joining_date"] == ""
        joining_meta = result.field_metadata["employment.joining_date"]
        assert joining_meta["origin"] == "derived"
        assert joining_meta["source_refs"] == []
        assert "alternatives" not in joining_meta
        assert any("日付補完せず" in error for error in result.review["validation_errors"])

    def test_build_extraction_result_routes_position_conflict_to_review(self):
        raw = {
            "case_data": {
                "employment": {
                    "has_position": _field_value(False, "役職 無"),
                    "position_title": _field_value("Project Manager", "Project Manager"),
                },
            },
            "review": {"validation_errors": [], "missing_items": [], "findings": []},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["has_position"] is True
        assert result.display_case_data["employment"]["position_title"] == "Project Manager"
        has_position_meta = result.field_metadata["employment.has_position"]
        assert has_position_meta["origin"] == "derived"
        assert has_position_meta["source_refs"] == []
        assert "alternatives" not in has_position_meta
        assert result.review["expected_route"] == "needs_review"
        assert any("役職なしの根拠と役職名の根拠" in error for error in result.review["validation_errors"])

    def test_build_extraction_result_derives_has_position_true_when_false_has_no_source(self):
        raw = {
            "case_data": {
                "employment": {
                    "has_position": _field_value_without_ref(False),
                    "position_title": _field_value("Project Manager", "Project Manager"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["has_position"] is True
        assert result.display_case_data["employment"]["position_title"] == "Project Manager"
        has_position_meta = result.field_metadata["employment.has_position"]
        assert has_position_meta["origin"] == "derived"
        assert has_position_meta["source_refs"] == []
        assert "alternatives" not in has_position_meta

    def test_build_extraction_result_derives_has_position_true_from_title_without_refs(self):
        raw = {
            "case_data": {
                "employment": {
                    "has_position": _field_value(False, "役職 無"),
                    "position_title": _field_value_without_ref("Project Manager"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["has_position"] is True
        assert result.display_case_data["employment"]["position_title"] == "Project Manager"
        has_position_meta = result.field_metadata["employment.has_position"]
        assert has_position_meta["origin"] == "derived"
        assert has_position_meta["source_refs"] == []
        assert "alternatives" not in has_position_meta

    def test_build_extraction_result_aligns_has_position_true_from_title(self):
        raw = {
            "case_data": {
                "employment": {
                    "has_position": _field_value_without_ref(""),
                    "position_title": _field_value("Project Manager", "Project Manager"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["has_position"] is True
        assert result.display_case_data["employment"]["position_title"] == "Project Manager"
        has_position_meta = result.field_metadata["employment.has_position"]
        assert has_position_meta["origin"] == "derived"
        assert has_position_meta["source_refs"] == []
        assert "alternatives" not in has_position_meta

    def test_build_extraction_result_marks_matching_has_position_as_derived(self):
        raw = {
            "case_data": {
                "employment": {
                    "has_position": _field_value(True, "役職 有"),
                    "position_title": _field_value("Project Manager", "Project Manager"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["has_position"] is True
        has_position_meta = result.field_metadata["employment.has_position"]
        assert has_position_meta["origin"] == "derived"
        assert has_position_meta["source_refs"] == []
        assert "alternatives" not in has_position_meta

    def test_build_extraction_result_does_not_normalize_ambiguous_job_category_label(self):
        raw = {
            "case_data": {
                "employment": {
                    "job_category_primary": _field_value("技術者", "技術者"),
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["job_category_primary"] == "技術者"

    def test_build_extraction_result_clears_has_position_source_when_deriving_false(self):
        raw = {
            "case_data": {
                "employment": {
                    "has_position": _field_value(True, "役職 有"),
                    "position_title": _field_value("", ""),
                },
            },
            "review": {"validation_errors": [], "missing_items": [], "findings": []},
        }

        result = _build_extraction_result(raw)

        assert result.display_case_data["employment"]["has_position"] is False
        assert result.field_metadata["employment.has_position"]["source_refs"] == []
        assert result.field_metadata["employment.has_position"]["origin"] == "derived"
        assert "alternatives" not in result.field_metadata["employment.has_position"]
        assert result.review["expected_route"] == "needs_review"

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

    def test_build_extraction_result_marks_empty_string_as_no_value(self):
        raw = {
            "case_data": {
                "applicant": {
                    "name_roman": {
                        "value": "",
                        "origin": "document",
                        "source_ref": {
                            "document_id": "",
                            "page": 0,
                            "text_quote": "",
                            "confidence": 0,
                            "locations": [],
                        },
                    },
                },
            },
            "review": {},
        }

        result = _build_extraction_result(raw)

        assert result.field_metadata["applicant.name_roman"]["has_value"] is False

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
                "resolver_type": "source_ref_location",
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
        assert name_meta["has_value"] is True
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
    def test_partial_scope_failure_does_not_expose_error_body(
        self,
        mock_extract_scoped,
        mock_call_gemini,
        caplog,
    ):
        secret = "SECRET RESPONSE BODY"

        def scoped_result(scope, *_args, **_kwargs):
            if scope == "applicant_identity":
                raise genai_errors.ServerError(
                    503,
                    {"error": {"status": "UNAVAILABLE", "message": secret}},
                )
            if scope == "employer":
                return {"case_data": {"employer": {"name": _field_value("Example Inc.")}}}
            return {"case_data": {}}

        mock_extract_scoped.side_effect = scoped_result
        mock_call_gemini.return_value = {
            "missing_items": [],
            "validation_errors": [],
            "findings": [],
        }

        with caplog.at_level("WARNING", logger="extractors.gemini"):
            result = extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)

        assert secret not in caplog.text
        assert secret not in json.dumps(result.review, ensure_ascii=False)
        assert any("ServerError status=503" in error for error in result.review["validation_errors"])

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
    def test_sanitizes_auth_error_when_all_scopes_fail(self, mock_extract_scoped, caplog):
        mock_extract_scoped.side_effect = genai_errors.ClientError(
            403,
            {
                "error": {
                    "status": "PERMISSION_DENIED",
                    "message": "Your API key was reported as leaked.",
                },
            },
        )

        with caplog.at_level("WARNING", logger="extractors.gemini"):
            try:
                extract_all_scopes(MagicMock(), [], _CASE_META, _DOCUMENTS)
            except RuntimeError as exc:
                assert "Gemini API key is invalid or not permitted" in str(exc)
                assert "reported as leaked" not in str(exc)
            else:
                raise AssertionError("extract_all_scopes should fail when all scopes fail")

        assert "ClientError status=403" in caplog.text
        assert "reported as leaked" not in caplog.text


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

    def test_carries_origin(self):
        case_data = {
            "applicant": {
                "name_roman": {
                    "value": "TANAKA TARO",
                    "origin": "document",
                    "source_refs": [
                        {"document_id": "doc_p", "page": 1, "text_quote": "TANAKA TARO", "confidence": 0.95}
                    ],
                }
            }
        }

        result = _extract_field_metadata(case_data)

        assert result["applicant.name_roman"]["origin"] == "document"

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
            "origin": "document",
            "source_refs": [
                {
                    "document_id": "doc_p",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.95,
                }
            ],
        }

    def test_preserves_origin_and_locations(self):
        raw = {
            "value": "TANAKA TARO",
            "origin": "document",
            "source_ref": {
                "document_id": "doc_p",
                "page": "1",
                "text_quote": "TANAKA TARO",
                "confidence": "0.95",
                "locations": [
                    {
                        "type": "pdf_bbox",
                        "page": "1",
                        "bbox": {
                            "y_min": "100",
                            "x_min": "200",
                            "y_max": "130",
                            "x_max": "260",
                        },
                    },
                    {"type": "xlsx_cell", "anchor_id": "Applicant!B2"},
                ],
            },
        }

        result = _unflatten_field_values(raw)

        assert result == {
            "value": "TANAKA TARO",
            "origin": "document",
            "source_refs": [
                {
                    "document_id": "doc_p",
                    "page": 1,
                    "text_quote": "TANAKA TARO",
                    "confidence": 0.95,
                    "locations": [
                        {
                            "type": "pdf_bbox",
                            "page": 1,
                            "bbox": {
                                "y_min": 100.0,
                                "x_min": 200.0,
                                "y_max": 130.0,
                                "x_max": 260.0,
                            },
                        },
                        {"type": "xlsx_cell", "anchor_id": "Applicant!B2"},
                    ],
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
        assert result == {"value": "", "origin": "derived", "source_refs": []}

    def test_marks_nonempty_inferred_string_without_valid_ref_as_derived(self):
        raw = {
            "value": "TANAKA TARO",
            "source_ref": {
                "document_id": "",
                "page": 0,
                "text_quote": "",
                "confidence": 0,
                "locations": [],
            },
        }

        result = _unflatten_field_values(raw)

        assert result == {
            "value": "TANAKA TARO",
            "origin": "derived",
            "source_refs": [],
        }

    def test_marks_typed_default_without_valid_ref_as_derived(self):
        raw = {
            "value": False,
            "source_ref": {
                "document_id": "",
                "page": 0,
                "text_quote": "",
                "confidence": 0,
                "locations": [],
            },
        }

        result = _unflatten_field_values(raw)

        assert result == {"value": False, "origin": "derived", "source_refs": []}

    def test_normalizes_alternatives(self):
        raw = {
            "value": "250000",
            "origin": "document",
            "source_ref": {
                "document_id": "doc_offer",
                "page": 1,
                "text_quote": "Monthly salary 250000",
                "confidence": 0.95,
                "locations": [],
            },
            "alternatives": [
                {
                    "value": "230000",
                    "origin": "document",
                    "source_ref": {
                        "document_id": "doc_resume",
                        "page": "2",
                        "text_quote": "Salary 230000",
                        "confidence": "0.82",
                        "locations": [],
                    },
                }
            ],
        }

        result = _unflatten_field_values(raw)

        assert result["alternatives"] == [
            {
                "value": "230000",
                "origin": "document",
                "source_refs": [
                    {
                        "document_id": "doc_resume",
                        "page": 2,
                        "text_quote": "Salary 230000",
                        "confidence": 0.82,
                        "locations": [],
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
                "origin": "document",
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
