"""extractors.xlsx のユニットテスト。openpyxl でxlsxを動的生成。"""

import io

import openpyxl

from extractors.xlsx import extract_xlsx
from extractors.types import OcrResult


def _make_xlsx(sheets: dict[str, list[list]]) -> bytes:
    """テスト用xlsxをメモリ上で生成。sheets = {シート名: [[行データ], ...]}"""
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        if first:
            ws = wb.active
            ws.title = name
            first = False
        else:
            ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestExtractXlsx:
    def test_basic_extraction(self):
        data = _make_xlsx({"Sheet1": [["Name", "Age"], ["Taro", 30]]})
        result = extract_xlsx(data, document_id="doc_x01")

        assert isinstance(result, OcrResult)
        assert result.document_id == "doc_x01"
        assert len(result.pages) == 1
        assert "Name" in result.pages[0].text
        assert "Taro" in result.pages[0].text
        assert "30" in result.pages[0].text

    def test_page_number_starts_at_one(self):
        data = _make_xlsx({"Sheet1": [["hello"]]})
        result = extract_xlsx(data, document_id="doc_x02")
        assert result.pages[0].page_number == 1

    def test_sheet_title_in_text(self):
        data = _make_xlsx({"申請人情報": [["氏名", "田中太郎"]]})
        result = extract_xlsx(data, document_id="doc_x03")
        assert "[Sheet: 申請人情報]" in result.pages[0].text

    def test_multiple_sheets(self):
        data = _make_xlsx({
            "Sheet1": [["A", "B"]],
            "Sheet2": [["C", "D"]],
            "Sheet3": [["E", "F"]],
        })
        result = extract_xlsx(data, document_id="doc_x04")

        assert len(result.pages) == 3
        for i, page in enumerate(result.pages):
            assert page.page_number == i + 1

        assert "A" in result.pages[0].text
        assert "C" in result.pages[1].text
        assert "E" in result.pages[2].text

    def test_sheet_name_filter(self):
        data = _make_xlsx({
            "Sheet1": [["A"]],
            "Sheet2": [["B"]],
        })
        result = extract_xlsx(data, document_id="doc_x05", sheet_name="Sheet2")

        assert len(result.pages) == 1
        assert "B" in result.pages[0].text
        assert "[Sheet: Sheet2]" in result.pages[0].text

    def test_sheet_name_not_found_returns_all(self):
        data = _make_xlsx({
            "Sheet1": [["A"]],
            "Sheet2": [["B"]],
        })
        result = extract_xlsx(data, document_id="doc_x06", sheet_name="NoSuchSheet")
        assert len(result.pages) == 2

    def test_empty_sheet_excluded(self):
        data = _make_xlsx({
            "Data": [["value"]],
            "Empty": [],
        })
        result = extract_xlsx(data, document_id="doc_x07")
        assert len(result.pages) == 1
        assert "[Sheet: Data]" in result.pages[0].text

    def test_none_cells_skipped(self):
        data = _make_xlsx({"Sheet1": [[None, "Hello", None, "World"]]})
        result = extract_xlsx(data, document_id="doc_x08")
        assert "Hello" in result.pages[0].text
        assert "World" in result.pages[0].text

    def test_words_list_is_empty(self):
        """xlsx抽出ではwordsは空リスト（バウンディングボックスなし）。"""
        data = _make_xlsx({"Sheet1": [["test"]]})
        result = extract_xlsx(data, document_id="doc_x09")
        assert result.pages[0].words == []
