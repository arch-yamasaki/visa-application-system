"""extractors.vision のユニットテスト。Vision API はモックで置き換え。"""

from unittest.mock import MagicMock, patch

import pymupdf

from extractors.types import OcrResult
from extractors.vision import ocr_document, ocr_image, ocr_pdf


# ---------- ヘルパー ---------------------------------------------------


def _make_text_pdf(text: str = "テスト文字列が二十文字以上含まれています") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=12, fontname="japan")
    data = doc.tobytes()
    doc.close()
    return data


def _make_image_only_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(10, 10, 190, 190))
    shape.finish(color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    shape.commit()
    data = doc.tobytes()
    doc.close()
    return data


def _mock_vertex(x, y):
    v = MagicMock()
    v.x = x
    v.y = y
    return v


def _build_vision_response(text: str = "OCR結果", confidence: float = 0.95):
    """Vision API のレスポンスをモックで構築。"""
    symbol = MagicMock()
    symbol.text = text

    word = MagicMock()
    word.symbols = [symbol]
    word.confidence = confidence
    word.bounding_box.vertices = [
        _mock_vertex(10, 20),
        _mock_vertex(100, 20),
        _mock_vertex(100, 50),
        _mock_vertex(10, 50),
    ]

    paragraph = MagicMock()
    paragraph.words = [word]

    block = MagicMock()
    block.paragraphs = [paragraph]

    page = MagicMock()
    page.blocks = [block]

    annotation = MagicMock()
    annotation.pages = [page]
    annotation.text = text

    response = MagicMock()
    response.full_text_annotation = annotation
    return response


# ---------- ocr_image --------------------------------------------------


class TestOcrImage:
    @patch("extractors.vision.vision.ImageAnnotatorClient")
    def test_returns_ocr_result(self, mock_client_class):
        mock_client = MagicMock()
        mock_client.document_text_detection.return_value = _build_vision_response("パスポート")
        mock_client_class.return_value = mock_client

        result = ocr_image(b"fake_image_bytes", document_id="doc_img01")

        assert isinstance(result, OcrResult)
        assert result.document_id == "doc_img01"
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert len(result.pages[0].words) == 1
        assert result.pages[0].words[0].text == "パスポート"

    @patch("extractors.vision.vision.ImageAnnotatorClient")
    def test_bbox_dimensions(self, mock_client_class):
        mock_client = MagicMock()
        mock_client.document_text_detection.return_value = _build_vision_response("テスト")
        mock_client_class.return_value = mock_client

        result = ocr_image(b"fake", document_id="doc_bbox")
        word = result.pages[0].words[0]
        assert word.bbox.x == 10
        assert word.bbox.y == 20
        assert word.bbox.width == 90  # 100 - 10
        assert word.bbox.height == 30  # 50 - 20

    @patch("extractors.vision.vision.ImageAnnotatorClient")
    def test_confidence_is_passed(self, mock_client_class):
        mock_client = MagicMock()
        mock_client.document_text_detection.return_value = _build_vision_response("w", confidence=0.88)
        mock_client_class.return_value = mock_client

        result = ocr_image(b"fake", document_id="doc_c")
        assert result.pages[0].words[0].confidence == 0.88

    @patch("extractors.vision.vision.ImageAnnotatorClient")
    def test_empty_annotation_returns_empty(self, mock_client_class):
        mock_client = MagicMock()
        response = MagicMock()
        response.full_text_annotation = None
        mock_client.document_text_detection.return_value = response
        mock_client_class.return_value = mock_client

        result = ocr_image(b"fake", document_id="doc_empty")
        assert result.pages == []


# ---------- ocr_document -----------------------------------------------


class TestOcrDocument:
    @patch("extractors.vision.extract_text")
    @patch("extractors.vision.has_text_layer", return_value=True)
    def test_pdf_with_text_layer_uses_extract_text(self, mock_has_text, mock_extract):
        """テキストレイヤーありPDF → extract_text が呼ばれる。"""
        mock_extract.return_value = OcrResult(document_id="doc_t", pages=[])
        pdf = _make_text_pdf()

        result = ocr_document(pdf, "test.pdf", "doc_t")

        mock_has_text.assert_called_once_with(pdf)
        mock_extract.assert_called_once_with(pdf, "doc_t")
        assert isinstance(result, OcrResult)

    @patch("extractors.vision.ocr_pdf")
    @patch("extractors.vision.has_text_layer", return_value=False)
    def test_pdf_without_text_layer_uses_ocr_pdf(self, mock_has_text, mock_ocr_pdf):
        """テキストレイヤーなしPDF → ocr_pdf が呼ばれる。"""
        mock_ocr_pdf.return_value = OcrResult(document_id="doc_o", pages=[])
        pdf = _make_image_only_pdf()

        result = ocr_document(pdf, "scan.pdf", "doc_o")

        mock_has_text.assert_called_once_with(pdf)
        mock_ocr_pdf.assert_called_once_with(pdf, "doc_o")
        assert isinstance(result, OcrResult)

    @patch("extractors.vision.ocr_image")
    def test_image_file_uses_ocr_image(self, mock_ocr_image):
        """画像ファイル → ocr_image が呼ばれる。"""
        mock_ocr_image.return_value = OcrResult(document_id="doc_i", pages=[])

        result = ocr_document(b"fake_png", "passport.png", "doc_i")

        mock_ocr_image.assert_called_once_with(b"fake_png", "doc_i")
        assert isinstance(result, OcrResult)

    @patch("extractors.vision.ocr_image")
    def test_jpg_file_uses_ocr_image(self, mock_ocr_image):
        """JPGファイルも ocr_image が呼ばれる。"""
        mock_ocr_image.return_value = OcrResult(document_id="doc_j", pages=[])

        ocr_document(b"fake_jpg", "photo.JPG", "doc_j")

        mock_ocr_image.assert_called_once_with(b"fake_jpg", "doc_j")
