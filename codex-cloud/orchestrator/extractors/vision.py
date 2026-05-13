"""Google Cloud Vision API によるOCR。"""

import pymupdf
from google.cloud import vision

from .pdf_text import has_text_layer, extract_text
from .types import BoundingBox, OcrResult, PageResult, WordResult


def _vertices_to_bbox(vertices) -> BoundingBox:
    """Vision API の boundingBox.vertices を BoundingBox に変換。"""
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]
    x_min, y_min = min(xs), min(ys)
    return BoundingBox(x=x_min, y=y_min, width=max(xs) - x_min, height=max(ys) - y_min)


def ocr_image(image_bytes: bytes, document_id: str) -> OcrResult:
    """画像1枚のOCR。DOCUMENT_TEXT_DETECTION。"""
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)
    annotation = response.full_text_annotation

    if not annotation or not annotation.pages:
        return OcrResult(document_id=document_id)

    pages: list[PageResult] = []
    for i, page in enumerate(annotation.pages):
        words: list[WordResult] = []
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    text = "".join(s.text for s in word.symbols)
                    bbox = _vertices_to_bbox(word.bounding_box.vertices)
                    words.append(WordResult(
                        text=text, bbox=bbox, confidence=word.confidence,
                    ))
        full_text = annotation.text if len(annotation.pages) == 1 else ""
        pages.append(PageResult(page_number=i + 1, text=full_text, words=words))

    return OcrResult(document_id=document_id, pages=pages)


def ocr_pdf(pdf_bytes: bytes, document_id: str) -> OcrResult:
    """PDFのOCR。ページごとに画像化してVision APIで処理。"""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages: list[PageResult] = []

    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        page_result = ocr_image(img_bytes, document_id=document_id)
        if page_result.pages:
            pr = page_result.pages[0]
            pages.append(PageResult(
                page_number=i + 1, text=pr.text, words=pr.words,
            ))
        else:
            pages.append(PageResult(page_number=i + 1, text=""))

    doc.close()
    return OcrResult(document_id=document_id, pages=pages)


def ocr_document(file_bytes: bytes, file_name: str, document_id: str) -> OcrResult:
    """ファイル形式を判定して適切なOCR関数を呼ぶ統合関数。"""
    lower = file_name.lower()

    if lower.endswith(".pdf"):
        if has_text_layer(file_bytes):
            return extract_text(file_bytes, document_id)
        return ocr_pdf(file_bytes, document_id)

    # 画像ファイル
    return ocr_image(file_bytes, document_id)
