"""anchor_resolver のユニットテスト。"""

import pymupdf

from extractors.anchor_resolver import resolve_anchors, sync_bbox_anchors


def _pdf_with_text(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    y = 40
    for line in lines:
        page.insert_text((40, y), line, fontsize=12)
        y += 30
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _pdf_with_pages(pages: list[list[str]], width: int = 300) -> bytes:
    # 注意: insert_text の標準フォントはCJKを描画できないため、
    # 検索対象の文字列はASCIIにする(日本語はtext layerに残らない)。
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=width, height=200)
        y = 40
        for line in lines:
            page.insert_text((40, y), line, fontsize=12)
            y += 30
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_resolve_anchors_adds_pdf_text_layer_bbox():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": _pdf_with_text(["AMIT TAMANG"])})
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["resolver_type"] == "pdf_text_layer"
    assert ref["anchor"]["page"] == 1
    assert ref["anchor"]["bbox"] == ref["bbox"]
    assert ref["bbox"]["x_min"] < ref["bbox"]["x_max"]
    assert ref["bbox"]["y_min"] < ref["bbox"]["y_max"]


def test_resolve_anchors_adds_pdf_text_layer_bbox_to_alternative_ref():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "250000",
                    "confidence": 0.9,
                }
            ],
            "alternatives": [
                {
                    "value": "230000",
                    "source_refs": [
                        {
                            "document_id": "doc_pdf",
                            "page": 1,
                            "text_quote": "230000",
                            "confidence": 0.8,
                        }
                    ],
                }
            ],
        }
    }

    result = resolve_anchors(
        field_metadata,
        {"doc_pdf": _pdf_with_text(["Offer salary 250000", "Resume salary 230000"])},
    )
    alt_ref = result["employment.monthly_salary"]["alternatives"][0]["source_refs"][0]

    assert alt_ref["anchor"]["status"] == "resolved"
    assert alt_ref["anchor"]["resolver_type"] == "pdf_text_layer"
    assert alt_ref["anchor"]["bbox"] == alt_ref["bbox"]


def test_resolve_anchors_uses_unique_pdf_match_on_other_page():
    field_metadata = {
        "employer.postal_code": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 2,
                    "text_quote": "151-8570",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(
        field_metadata,
        {"doc_pdf": _pdf_with_pages([["会社概要 151-8570"], ["支店一覧"]])},
    )
    ref = result["employer.postal_code"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["page"] == 1
    assert ref["anchor"]["resolver_type"] == "pdf_text_layer"


def test_resolve_anchors_marks_duplicate_pdf_text_as_ambiguous():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(
        field_metadata,
        {"doc_pdf": _pdf_with_text(["基本給 260000", "月額合計 260000"])},
    )
    ref = result["employment.monthly_salary"]["source_refs"][0]

    assert "bbox" not in ref
    anchor = ref["anchor"]
    assert anchor["type"] == "pdf_bbox"
    assert anchor["status"] == "ambiguous"
    assert anchor["resolver_type"] == "pdf_text_layer"
    assert anchor["match_count"] == 2
    candidates = anchor["candidates"]
    assert len(candidates) == 2
    for candidate in candidates:
        assert candidate["page"] == 1
        assert set(candidate["bbox"]) == {"y_min", "x_min", "y_max", "x_max"}
    assert candidates[0]["bbox"] != candidates[1]["bbox"]


def test_resolve_anchors_matches_quote_across_parentheses():
    field_metadata = {
        "applicant.employment_history.0.end_date": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "October 2024",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(
        field_metadata,
        {"doc_pdf": _pdf_with_text(["Engineer (May 2024 - October 2024)"])},
    )
    ref = result["applicant.employment_history.0.end_date"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["resolver_type"] == "pdf_text_layer"


def test_resolve_anchors_caps_ambiguous_candidates_at_three():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(
        field_metadata,
        {"doc_pdf": _pdf_with_text([f"項目{i} 260000" for i in range(5)])},
    )
    anchor = result["employment.monthly_salary"]["source_refs"][0]["anchor"]

    assert anchor["status"] == "ambiguous"
    assert anchor["match_count"] == 5
    assert len(anchor["candidates"]) == 3


def test_sync_bbox_anchors_preserves_legacy_bbox():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                    "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                }
            ]
        }
    }

    result = sync_bbox_anchors(field_metadata)
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "pdf_bbox",
        "status": "resolved",
        "resolver_type": "gemini_bbox",
        "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
        "match_count": 1,
        "page": 1,
    }


def test_sync_bbox_anchors_preserves_alternative_legacy_bbox():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [],
            "alternatives": [
                {
                    "value": "230000",
                    "source_refs": [
                        {
                            "document_id": "doc_pdf",
                            "page": 2,
                            "text_quote": "230000",
                            "confidence": 0.8,
                            "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                        }
                    ],
                }
            ],
        }
    }

    result = sync_bbox_anchors(field_metadata)
    ref = result["employment.monthly_salary"]["alternatives"][0]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "pdf_bbox",
        "status": "resolved",
        "resolver_type": "gemini_bbox",
        "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
        "match_count": 1,
        "page": 2,
    }


def test_sync_bbox_anchors_does_not_promote_ambiguous_anchor():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                    "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                    "anchor": {
                        "type": "pdf_bbox",
                        "status": "ambiguous",
                        "resolver_type": "pdf_text_layer",
                        "match_count": 2,
                    },
                }
            ]
        }
    }

    result = sync_bbox_anchors(field_metadata)
    ref = result["employment.monthly_salary"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "pdf_bbox",
        "status": "ambiguous",
        "resolver_type": "pdf_text_layer",
        "match_count": 2,
    }


def test_resolve_anchors_does_not_promote_ambiguous_anchor_with_bbox():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                    "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                    "anchor": {
                        "type": "pdf_bbox",
                        "status": "ambiguous",
                        "resolver_type": "pdf_text_layer",
                        "match_count": 2,
                    },
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": _pdf_with_text(["260000"])})
    ref = result["employment.monthly_salary"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "pdf_bbox",
        "status": "ambiguous",
        "resolver_type": "pdf_text_layer",
        "match_count": 2,
    }


def test_resolve_anchors_adds_xlsx_cell_anchor():
    field_metadata = {
        "employment.monthly_salary": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 1,
                    "text_quote": "260000",
                    "confidence": 0.9,
                }
            ]
        }
    }
    xlsx_index = {
        "doc_xlsx": [
            {
                "type": "xlsx_cell",
                "sheet_name": "Sheet1",
                "cell": "B2",
                "row": 2,
                "col": 2,
                "text": "260000",
                "anchor_id": "Sheet1!B2",
            }
        ]
    }

    result = resolve_anchors(field_metadata, {}, xlsx_index, {})
    ref = result["employment.monthly_salary"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "xlsx_cell",
        "status": "resolved",
        "resolver_type": "xlsx_cell_index",
        "match_count": 1,
        "anchor_id": "Sheet1!B2",
        "sheet_name": "Sheet1",
        "cell": "B2",
        "row": 2,
        "col": 2,
    }


def _xlsx_cell(sheet: str, cell: str, row: int, col: int, text: str) -> dict:
    return {
        "type": "xlsx_cell",
        "sheet_name": sheet,
        "cell": cell,
        "row": row,
        "col": col,
        "text": text,
        "anchor_id": f"{sheet}!{cell}",
    }


def test_resolve_anchors_resolves_multi_cell_quote_with_tab():
    """質問セル+回答セルがタブ連結されたquoteは、回答セルで解決する。"""
    field_metadata = {
        "applicant.birth_place": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 5,
                    "text_quote": "Place of birth　出生地\tArghakhanchi",
                    "confidence": 0.9,
                }
            ]
        }
    }
    xlsx_index = {
        "doc_xlsx": [
            _xlsx_cell("Bhawana Khanal", "C3", 3, 3, "Place of birth　出生地"),
            _xlsx_cell("Bhawana Khanal", "D3", 3, 4, "Arghakhanchi"),
        ]
    }

    result = resolve_anchors(field_metadata, {}, xlsx_index, {})
    anchor = result["applicant.birth_place"]["source_refs"][0]["anchor"]

    assert anchor["status"] == "resolved"
    assert anchor["anchor_id"] == "Bhawana Khanal!D3"


def test_resolve_anchors_narrows_multi_cell_quote_by_question_row():
    """回答セルが複数シートに一致しても、同じ行に質問セルがある方へ絞り込む。"""
    field_metadata = {
        "applicant.birth_place": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 5,
                    "text_quote": "Place of birth　出生地\tDhankuta",
                    "confidence": 0.9,
                }
            ]
        }
    }
    xlsx_index = {
        "doc_xlsx": [
            # 出身地(別の質問)の行にも同じ値がある
            _xlsx_cell("Kushang", "C6", 6, 3, "Hometown city 出身地"),
            _xlsx_cell("Kushang", "D6", 6, 4, "Dhankuta"),
            _xlsx_cell("Kushang", "C3", 3, 3, "Place of birth　出生地"),
            _xlsx_cell("Kushang", "D3", 3, 4, "Dhankuta"),
        ]
    }

    result = resolve_anchors(field_metadata, {}, xlsx_index, {})
    anchor = result["applicant.birth_place"]["source_refs"][0]["anchor"]

    assert anchor["status"] == "resolved"
    assert anchor["anchor_id"] == "Kushang!D3"


def test_resolve_anchors_does_not_substring_match_short_quote():
    field_metadata = {
        "employer.has_corporate_number": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 1,
                    "text_quote": "有",
                    "confidence": 0.9,
                }
            ]
        }
    }
    xlsx_index = {
        "doc_xlsx": [
            {
                "type": "xlsx_cell",
                "sheet_name": "Sheet1",
                "cell": "A1",
                "row": 1,
                "col": 1,
                "text": "有効期限",
                "anchor_id": "Sheet1!A1",
            }
        ]
    }

    result = resolve_anchors(field_metadata, {}, xlsx_index, {})
    ref = result["employer.has_corporate_number"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "xlsx_cell",
        "status": "not_found",
        "resolver_type": "xlsx_cell_index",
        "match_count": 0,
    }


def test_resolve_anchors_allows_exact_short_quote():
    field_metadata = {
        "employer.has_corporate_number": {
            "source_refs": [
                {
                    "document_id": "doc_xlsx",
                    "page": 1,
                    "text_quote": "有",
                    "confidence": 0.9,
                }
            ]
        }
    }
    xlsx_index = {
        "doc_xlsx": [
            {
                "type": "xlsx_cell",
                "sheet_name": "Sheet1",
                "cell": "B2",
                "row": 2,
                "col": 2,
                "text": "有",
                "anchor_id": "Sheet1!B2",
            }
        ]
    }

    result = resolve_anchors(field_metadata, {}, xlsx_index, {})
    ref = result["employer.has_corporate_number"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["cell"] == "B2"


def test_resolve_anchors_is_idempotent_after_cross_page_resolution():
    pdf_bytes = _pdf_with_pages([["AMIT TAMANG"], ["支店一覧"]])
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 2,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        }
    }

    first = resolve_anchors(field_metadata, {"doc_pdf": pdf_bytes})
    ref = first["applicant.name_roman"]["source_refs"][0]
    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["page"] == 1
    first_anchor = dict(ref["anchor"])
    first_bbox = dict(ref["bbox"])

    second = resolve_anchors(first, {"doc_pdf": pdf_bytes})
    ref = second["applicant.name_roman"]["source_refs"][0]

    # 再実行しても anchor.page が ref.page(=2) に巻き戻らない
    assert ref["anchor"] == first_anchor
    assert ref["bbox"] == first_bbox
    # source_ref.page は抽出根拠としてそのまま残る
    assert ref["page"] == 2


def test_resolve_anchors_mirrors_legacy_bbox_with_ref_page():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 3,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                    "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {})
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "pdf_bbox",
        "status": "resolved",
        "resolver_type": "existing_bbox",
        "bbox": {"y_min": 100, "x_min": 200, "y_max": 130, "x_max": 260},
        "match_count": 1,
        "page": 3,
    }


def test_resolve_anchors_prefers_full_quote_on_other_page_over_number_fallback():
    # 指定ページには quote 内の数値パターンだけが別文脈で存在し、
    # フル quote は別ページに一意に存在する。
    pdf_bytes = _pdf_with_pages([["BRANCH 151-8570"], ["HEADOFFICE 151-8570"]])
    field_metadata = {
        "employer.postal_code": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "HEADOFFICE 151-8570",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": pdf_bytes})
    ref = result["employer.postal_code"]["source_refs"][0]

    # 数値パターンfallbackが指定ページの別の151-8570に付くのではなく、
    # フル quote のクロスページ一意一致が勝つ
    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["page"] == 2
    assert ref["anchor"]["resolver_type"] == "pdf_text_layer"


def test_resolve_anchors_keeps_ambiguous_full_quote_without_weaker_fallback():
    pdf_bytes = _pdf_with_pages(
        [["SHIBUYA 151-8570", "SHIBUYA 151-8570"], ["151-8570"]]
    )
    field_metadata = {
        "employer.postal_code": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "SHIBUYA 151-8570",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": pdf_bytes})
    ref = result["employer.postal_code"]["source_refs"][0]

    # フル quote が指定ページで複数一致なら、弱いtargetや他ページで無理に確定しない
    assert ref["anchor"]["status"] == "ambiguous"
    assert ref["anchor"]["match_count"] == 2
    assert "bbox" not in ref


def _long_quote_words(count: int) -> list[str]:
    return [f"SEGMENT{i:02d}XYZ" for i in range(count)]


def test_resolve_anchors_matches_long_quote_exactly():
    # 80文字超の quote でもフル quote の完全一致で解決できる
    words = _long_quote_words(8)  # 12文字 x 8語 + 空白7 = 103文字
    quote = " ".join(words)
    assert len(quote) > 80
    pdf_bytes = _pdf_with_pages(
        [[" ".join(words[0:3]), " ".join(words[3:6]), " ".join(words[6:8])]],
        width=800,
    )
    field_metadata = {
        "employment.activity_details": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": quote,
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": pdf_bytes})
    ref = result["employment.activity_details"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["page"] == 1


def test_resolve_anchors_falls_back_to_word_boundary_prefix_for_long_quote():
    # フル quote が原本と一致しない場合(quote末尾に余計な語がある等)でも、
    # 単語境界で切った80文字プレフィックスで解決できる
    words = _long_quote_words(8)
    quote = " ".join(words) + " TRAILING_NOT_IN_PDF"
    pdf_bytes = _pdf_with_pages(
        [[" ".join(words[0:3]), " ".join(words[3:6]), " ".join(words[6:8])]],
        width=800,
    )
    field_metadata = {
        "employment.activity_details": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": quote,
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": pdf_bytes})
    ref = result["employment.activity_details"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["page"] == 1


def test_resolve_anchors_searches_all_pages_when_page_missing():
    pdf_bytes = _pdf_with_pages([["会社概要"], ["AMIT TAMANG"]])
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        }
    }

    result = resolve_anchors(field_metadata, {"doc_pdf": pdf_bytes})
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"]["status"] == "resolved"
    assert ref["anchor"]["page"] == 2


def test_resolve_anchors_parses_pdf_once_per_document(monkeypatch):
    pdf_bytes = _pdf_with_pages([["page one"], ["AMIT TAMANG"], ["page three"]])
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 1,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        },
        "employer.name": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 3,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        },
        "employment.position_title": {
            "source_refs": [
                {
                    "document_id": "doc_pdf",
                    "page": 2,
                    "text_quote": "MISSING VALUE",
                    "confidence": 0.9,
                }
            ]
        },
    }

    open_calls = []
    original_open = pymupdf.open

    def counting_open(*args, **kwargs):
        open_calls.append(1)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(pymupdf, "open", counting_open)
    result = resolve_anchors(field_metadata, {"doc_pdf": pdf_bytes})

    # クロスページ探索を含む複数refでも、同一文書のPDFパースは1回
    assert len(open_calls) == 1
    assert result["applicant.name_roman"]["source_refs"][0]["anchor"]["page"] == 2
    assert result["employer.name"]["source_refs"][0]["anchor"]["page"] == 2
    assert result["employment.position_title"]["source_refs"][0]["anchor"]["status"] == "not_found"


def test_resolve_anchors_marks_duplicate_docx_blocks_as_ambiguous():
    field_metadata = {
        "applicant.name_roman": {
            "source_refs": [
                {
                    "document_id": "doc_docx",
                    "page": 1,
                    "text_quote": "AMIT TAMANG",
                    "confidence": 0.9,
                }
            ]
        }
    }
    docx_index = {
        "doc_docx": [
            {"type": "docx_block", "paragraph_index": 0, "text": "AMIT TAMANG", "anchor_id": "p-0"},
            {"type": "docx_block", "paragraph_index": 1, "text": "AMIT TAMANG", "anchor_id": "p-1"},
        ]
    }

    result = resolve_anchors(field_metadata, {}, {}, docx_index)
    ref = result["applicant.name_roman"]["source_refs"][0]

    assert ref["anchor"] == {
        "type": "docx_block",
        "status": "ambiguous",
        "resolver_type": "docx_block_index",
        "match_count": 2,
    }
