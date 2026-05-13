"""extractors.gemini のユニットテスト。Gemini API はモックで置き換え。"""

import json
from unittest.mock import MagicMock, patch

from extractors.gemini import (
    _build_ocr_context,
    _map_field_metadata,
    extract_pdf_direct,
    extract_text_only,
    extract_with_images,
)
from extractors.prompt_template import build_extraction_prompt
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

_GEMINI_RESPONSE = {
    "case_data": {
        "applicant": {"name_roman": "TANAKA TARO", "nationality": "JP"},
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

    def test_no_documents_shows_placeholder(self):
        prompt = build_extraction_prompt(_CASE_META, [])
        assert "(なし)" in prompt


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


class TestExtractTextOnly:
    @patch("extractors.gemini._get_client")
    def test_returns_extraction_result(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE
        )
        mock_get_client.return_value = mock_client

        result = extract_text_only(_make_ocr_results(), _CASE_META, _DOCUMENTS)

        assert isinstance(result, ExtractionResult)
        assert result.case_data["applicant"]["name_roman"] == "TANAKA TARO"
        assert result.review["summary"] == "問題なし"
        mock_client.models.generate_content.assert_called_once()

    @patch("extractors.gemini._get_client")
    def test_prompt_contains_ocr_text(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE
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
            _GEMINI_RESPONSE
        )
        mock_get_client.return_value = mock_client
        mock_from_bytes.return_value = "pdf_part"

        pdf_contents = [("doc_p", b"fake_pdf_bytes")]
        result = extract_pdf_direct(pdf_contents, _CASE_META, _DOCUMENTS)

        assert isinstance(result, ExtractionResult)
        assert result.case_data["applicant"]["nationality"] == "JP"
        mock_from_bytes.assert_called_once_with(
            data=b"fake_pdf_bytes", mime_type="application/pdf"
        )

    @patch("extractors.gemini.types.Part.from_bytes")
    @patch("extractors.gemini._get_client")
    def test_multiple_pdfs(self, mock_get_client, mock_from_bytes):
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _mock_gemini_response(
            _GEMINI_RESPONSE
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
            _GEMINI_RESPONSE
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
            _GEMINI_RESPONSE
        )
        mock_get_client.return_value = mock_client
        mock_from_bytes.return_value = "img_part"

        jpg_bytes = b"\xff\xd8\xff" + b"\x00" * 100
        extract_with_images(
            _make_ocr_results(), [("doc_p", jpg_bytes)], _CASE_META
        )

        mock_from_bytes.assert_called_once_with(data=jpg_bytes, mime_type="image/jpeg")


# ---------- _map_field_metadata -----------------------------------------


class TestMapFieldMetadata:
    def test_maps_bbox_from_ocr(self):
        raw_metadata = {
            "applicant.name_roman": {
                "source_refs": [
                    {
                        "document_id": "doc_p",
                        "page": "1",
                        "text_quote": "TANAKA",
                        "confidence": "0.95",
                    }
                ]
            }
        }
        ocr_results = _make_ocr_results()
        result = _map_field_metadata(raw_metadata, ocr_results)

        ref = result["applicant.name_roman"]["source_refs"][0]
        assert "bbox" in ref
        assert ref["bbox"]["x"] == 10
        assert ref["bbox"]["y"] == 20
        assert ref["bbox"]["width"] == 80

    def test_no_match_no_bbox(self):
        raw_metadata = {
            "some.field": {
                "source_refs": [
                    {"text_quote": "NONEXISTENT_TEXT", "confidence": "0.5"}
                ]
            }
        }
        result = _map_field_metadata(raw_metadata, _make_ocr_results())
        ref = result["some.field"]["source_refs"][0]
        assert "bbox" not in ref

    def test_empty_text_quote_skipped(self):
        raw_metadata = {
            "some.field": {"source_refs": [{"text_quote": "", "confidence": "0.5"}]}
        }
        result = _map_field_metadata(raw_metadata, _make_ocr_results())
        ref = result["some.field"]["source_refs"][0]
        assert "bbox" not in ref

    def test_empty_ocr_returns_unchanged(self):
        raw_metadata = {"f": {"source_refs": [{"text_quote": "X"}]}}
        result = _map_field_metadata(raw_metadata, [])
        assert result == raw_metadata

    def test_best_match_longest_word(self):
        """text_quote に複数の word がマッチする場合、最長の word を選ぶ。"""
        raw_metadata = {
            "applicant.name_roman": {
                "source_refs": [
                    {"text_quote": "TANAKA TARO", "confidence": "0.95"}
                ]
            }
        }
        ocr_results = _make_ocr_results()
        result = _map_field_metadata(raw_metadata, ocr_results)

        ref = result["applicant.name_roman"]["source_refs"][0]
        # "TANAKA" (6 chars) > "TARO" (4 chars) → TANAKA の bbox が使われる
        assert ref["bbox"]["x"] == 10
        assert ref["bbox"]["width"] == 80
