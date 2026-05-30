# 05 DOCX block anchor

## 目的

DOCX由来の証跡を、段落または表セル単位でハイライトできるようにする。

## 方針

DOCXはPDFのような厳密座標ではなく、レビューしやすい block highlight を優先する。

## 調査対象ファイル

| ファイル | 現状 |
|---|---|
| `backend/extractors/docx_text.py` | DOCXをテキスト化するが、paragraph/table/cell anchor は持たない |
| `backend/main.py` | DOCX preview HTML を生成する |
| `frontend/src/components/viewer/HtmlViewer.tsx` | HTML内の文字列検索で highlight する |
| `frontend/src/components/viewer/DocumentViewer.tsx` | file extension から HtmlViewer を選ぶ |
| `frontend/src/types/caseData.ts` | `SourceRef` 型に DOCX block 情報がない |

## source_ref 拡張案

段落:

```json
{
  "document_id": "doc_docx123",
  "page": 1,
  "text_quote": "月給 260,000円",
  "confidence": 0.9,
  "anchor_type": "docx_block",
  "paragraph_index": 12
}
```

表セル:

```json
{
  "document_id": "doc_docx123",
  "page": 1,
  "text_quote": "260,000円",
  "confidence": 0.9,
  "anchor_type": "docx_cell",
  "table_index": 0,
  "row": 3,
  "col": 1
}
```

## 作業計画

1. `backend/extractors/docx_text.py` で paragraph / table / row / col を保持する。
2. DOCX preview HTML に `data-paragraph-index`, `data-table-index`, `data-row`, `data-col` を埋める。
3. `SourceRef` 型に `anchor_type`, `paragraph_index`, `table_index`, `row`, `col` を追加する。
4. viewer 側で paragraph または cell に scroll して highlight する。
5. `text_quote` fallback は残す。

## 推奨

最初は Gemini に paragraph/table index を返させない。backend 側で `text_quote` が一意に見つかる場合だけ block anchor を補完する。

理由は、Gemini に DOM/preview 上の index を正確に返させるには、preview側の構造を prompt に渡す必要があり、schema と prompt が重くなるため。

## 受け入れ条件

- DOCX由来の主要fieldで、該当段落または表セルへ移動できる。
- Wordの厳密な見た目再現を目的にしない。
- PDF bbox の仕組みと混ぜない。

## リスク

- DOCXの段落分割が人間の見た目と一致しない場合がある
- 表内の改行や結合セルで row / col がずれる
- 同じ文言が複数段落にある場合、quoteだけでは決まらない
- Wordのページ番号とHTML previewの位置は一致しない

## 削除・整理候補

- DOCXにPDF bboxが付く前提の説明
- Office preview は文字検索だけで十分とする説明
