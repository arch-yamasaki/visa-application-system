"""Gemini 3 Flash structured extraction for visa application documents."""

import json
import os

from google import genai
from google.genai import types

from .prompt_template import build_extraction_prompt
from .types import ExtractionResult, OcrResult

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")



def _build_ocr_context(ocr_results: list[OcrResult]) -> str:
    sections = []
    for ocr in ocr_results:
        for page in ocr.pages:
            sections.append(
                f"--- document: {ocr.document_id}, page: {page.page_number} ---\n"
                f"{page.text}"
            )
    return "\n\n".join(sections)


def _get_client() -> genai.Client:
    return genai.Client()


def _call_gemini(client: genai.Client, contents: list, prompt: str) -> dict:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[*contents, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )
    parsed = json.loads(response.text)
    if isinstance(parsed, list) and len(parsed) == 1:
        parsed = parsed[0]
    return parsed


def _map_field_metadata(
    raw_metadata: dict, ocr_results: list[OcrResult]
) -> dict:
    """Enrich field_metadata with bounding boxes from OCR word coordinates."""
    word_index: list[tuple[str, int, str, object]] = []
    for ocr in ocr_results:
        for page in ocr.pages:
            for word in page.words:
                if word.bbox is not None:
                    word_index.append(
                        (ocr.document_id, page.page_number, word.text, word.bbox)
                    )

    if not word_index:
        return raw_metadata

    for field_path, meta in raw_metadata.items():
        for ref in meta.get("source_refs", []):
            text_quote = ref.get("text_quote", "")
            if not text_quote:
                continue
            best_match = None
            best_score = 0
            for doc_id, page_num, word_text, bbox in word_index:
                if word_text in text_quote or text_quote in word_text:
                    score = len(word_text)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "x": bbox.x,
                            "y": bbox.y,
                            "width": bbox.width,
                            "height": bbox.height,
                        }
            if best_match:
                ref["bbox"] = best_match

    return raw_metadata


def extract_text_only(
    ocr_results: list[OcrResult],
    case_meta: dict,
    documents: list[dict] | None = None,
    text_contents: list[tuple[str, str]] | None = None,
) -> ExtractionResult:
    """Pattern A: OCR text only."""
    prompt = build_extraction_prompt(case_meta, documents or [])
    ocr_context = _build_ocr_context(ocr_results)
    text_section = ""
    if text_contents:
        text_parts = []
        for doc_id, text in text_contents:
            text_parts.append(f"--- document: {doc_id} ---\n{text}")
        text_section = "\n\n## テキスト書類（xlsx/docx等）\n\n" + "\n\n".join(text_parts)
    full_prompt = f"{prompt}\n\n## 書類テキスト（OCR結果）\n\n{ocr_context}{text_section}"

    client = _get_client()
    raw = _call_gemini(client, [], full_prompt)

    field_metadata = _map_field_metadata(
        raw.get("field_metadata", {}), ocr_results
    )
    return ExtractionResult(
        case_data=raw.get("case_data", {}),
        review=raw.get("review", {}),
        field_metadata=field_metadata,
    )


def extract_pdf_direct(
    pdf_contents: list[tuple[str, bytes]],
    case_meta: dict,
    documents: list[dict] | None = None,
    text_contents: list[tuple[str, str]] | None = None,
) -> ExtractionResult:
    """Pattern B: PDF direct to Gemini."""
    prompt = build_extraction_prompt(case_meta, documents or [])
    parts = []
    # テキスト書類（xlsx, docx等）
    if text_contents:
        for doc_id, text in text_contents:
            parts.append(f"--- document: {doc_id} ---\n{text}")
    # PDF書類
    for doc_id, pdf_bytes in pdf_contents:
        parts.append(
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        )
        parts.append(f"(document_id: {doc_id})")

    client = _get_client()
    raw = _call_gemini(client, parts, prompt)

    return ExtractionResult(
        case_data=raw.get("case_data", {}),
        review=raw.get("review", {}),
        field_metadata=raw.get("field_metadata", {}),
    )


def extract_with_images(
    ocr_results: list[OcrResult],
    image_contents: list[tuple[str, bytes]],
    case_meta: dict,
    documents: list[dict] | None = None,
    text_contents: list[tuple[str, str]] | None = None,
) -> ExtractionResult:
    """Pattern C: OCR text + images."""
    prompt = build_extraction_prompt(case_meta, documents or [])
    ocr_context = _build_ocr_context(ocr_results)

    parts: list = []
    # テキスト書類（xlsx, docx等）
    if text_contents:
        for doc_id, text in text_contents:
            parts.append(f"--- document: {doc_id} ---\n{text}")
    parts.append(f"## 書類テキスト（OCR結果）\n\n{ocr_context}")
    for doc_id, img_bytes in image_contents:
        mime = "image/png" if img_bytes[:4] == b"\x89PNG" else "image/jpeg"
        parts.append(
            types.Part.from_bytes(data=img_bytes, mime_type=mime)
        )
        parts.append(f"(document_id: {doc_id})")

    client = _get_client()
    raw = _call_gemini(client, parts, prompt)

    field_metadata = _map_field_metadata(
        raw.get("field_metadata", {}), ocr_results
    )
    return ExtractionResult(
        case_data=raw.get("case_data", {}),
        review=raw.get("review", {}),
        field_metadata=field_metadata,
    )
