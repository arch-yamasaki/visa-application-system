"""extractors.pdf_text のユニットテスト。pymupdf でPDFを動的に生成。"""

import pymupdf

from extractors.pdf_text import extract_text, has_text_layer


def _make_text_pdf(text: str = "Hello World this is a test string") -> bytes:
    """テキストレイヤー付きの小さなPDFをメモリ上で生成。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def _make_image_only_pdf() -> bytes:
    """テキストレイヤーなし（画像のみ）のPDFを生成。"""
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    # 矩形を描画するだけ — テキストなし
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(10, 10, 190, 190))
    shape.finish(color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    shape.commit()
    data = doc.tobytes()
    doc.close()
    return data


# ---- has_text_layer ---------------------------------------------------


class TestHasTextLayer:
    def test_text_pdf_returns_true(self):
        pdf = _make_text_pdf("This text is long enough to pass the threshold easily")
        assert has_text_layer(pdf) is True

    def test_image_only_pdf_returns_false(self):
        pdf = _make_image_only_pdf()
        assert has_text_layer(pdf) is False

    def test_short_text_below_threshold_returns_false(self):
        """20文字未満のテキストレイヤー → False。"""
        pdf = _make_text_pdf("abc")
        assert has_text_layer(pdf) is False


# ---- extract_text -----------------------------------------------------


class TestExtractText:
    def test_extracts_text_and_words(self):
        text = "Extraction test content here"
        pdf = _make_text_pdf(text)
        result = extract_text(pdf, document_id="doc_test01")

        assert result.document_id == "doc_test01"
        assert len(result.pages) == 1

        page = result.pages[0]
        assert page.page_number == 1
        assert "Extraction" in page.text
        assert len(page.words) > 0

    def test_word_bbox_has_valid_dimensions(self):
        pdf = _make_text_pdf("BoundingBox validation string test")
        result = extract_text(pdf, document_id="doc_bbox")
        page = result.pages[0]

        for word in page.words:
            assert word.bbox.width > 0
            assert word.bbox.height > 0
            assert word.bbox.x >= 0
            assert word.bbox.y >= 0

    def test_multi_page_pdf(self):
        """複数ページPDFで各ページが正しく抽出される。"""
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 72), f"Page {i + 1} content for testing", fontsize=12)
        data = doc.tobytes()
        doc.close()

        result = extract_text(data, document_id="doc_multi")
        assert len(result.pages) == 3
        for i, page in enumerate(result.pages):
            assert page.page_number == i + 1
            assert f"Page {i + 1}" in page.text

    def test_empty_pdf_returns_empty_pages(self):
        """テキストなしPDFからは空のwordsが返る。"""
        pdf = _make_image_only_pdf()
        result = extract_text(pdf, document_id="doc_empty")
        assert len(result.pages) == 1
        assert result.pages[0].words == []

    def test_word_confidence_is_one(self):
        """PyMuPDFのテキスト抽出はconfidence=1.0。"""
        pdf = _make_text_pdf("confidence check for the extractor module")
        result = extract_text(pdf, document_id="doc_conf")
        for word in result.pages[0].words:
            assert word.confidence == 1.0
