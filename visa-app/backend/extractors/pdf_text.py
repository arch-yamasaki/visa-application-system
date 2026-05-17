"""PyMuPDF によるPDFテキストレイヤー抽出。"""

import pymupdf

from .types import BoundingBox, OcrResult, PageResult, WordResult

# テキストレイヤー判定の最小文字数しきい値
_MIN_TEXT_LENGTH = 20


def has_text_layer(pdf_bytes: bytes) -> bool:
    """PDFにテキストレイヤーがあるか判定。"""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total = sum(len(page.get_text().strip()) for page in doc)
    doc.close()
    return total >= _MIN_TEXT_LENGTH


def extract_text(pdf_bytes: bytes, document_id: str) -> OcrResult:
    """テキストレイヤーからテキスト+座標を抽出。"""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages: list[PageResult] = []

    for i, page in enumerate(doc):
        words: list[WordResult] = []
        for w in page.get_text("words"):
            x0, y0, x1, y1 = w[:4]
            words.append(WordResult(
                text=w[4],
                bbox=BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0),
                confidence=1.0,
            ))
        text = page.get_text().strip()
        pages.append(PageResult(page_number=i + 1, text=text, words=words))

    doc.close()
    return OcrResult(document_id=document_id, pages=pages)
