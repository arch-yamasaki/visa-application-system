# 04 XLSX cell anchor

## 目的

XLSX由来の証跡を、文字検索ではなく sheet / cell 単位でハイライトできるようにする。

## 現状

XLSXは backend でテキスト化され、preview HTML では表として表示される。証跡ジャンプは `text_quote` の文字検索に依存している。

このため、同じ値が複数セルにある場合や、別シートにある場合に不安定。

## 調査対象ファイル

| ファイル | 現状 |
|---|---|
| `backend/extractors/xlsx.py` | XLSXの値をテキスト化するが、証跡用の sheet/cell anchor は持たない |
| `backend/main.py` | XLSX preview HTML を生成する |
| `frontend/src/components/viewer/HtmlViewer.tsx` | HTML内の文字列検索で highlight する |
| `frontend/src/components/viewer/DocumentViewer.tsx` | file extension から HtmlViewer を選ぶ |
| `frontend/src/types/caseData.ts` | `SourceRef` 型に sheet/cell 情報がない |

## source_ref 拡張案

```json
{
  "document_id": "doc_xlsx123",
  "page": 1,
  "text_quote": "260000",
  "confidence": 0.9,
  "anchor_type": "xlsx_cell",
  "sheet_name": "Sheet1",
  "cell": "F12"
}
```

## 作業計画

1. `backend/extractors/xlsx.py` で sheet / row / col / cell address を保持できる形にする。
2. XLSX preview HTML に `data-sheet`, `data-row`, `data-col`, `data-cell` を埋める。
3. `SourceRef` 型に `anchor_type`, `sheet_name`, `cell` を追加する。
4. viewer 側で対象 sheet を開き、対象 cell に scroll して highlight する。
5. Gemini に cell address を直接出させるか、backend で quote から cell を解決するか決める。
6. 同じ値が複数セルにある場合は、周辺ラベルや列名を使う設計にする。

## 推奨

最初は backend で quote から cell を解決する方がよい。Gemini に cell address まで正確に出させると、promptとschemaが重くなる。

処理順は次がよい。

1. XLSX preview HTML に cell anchor を埋める
2. backend 側で一意に一致する quote だけ `xlsx_cell` anchor を補完する
3. 一意に決まらない場合は従来の `text_quote` fallback に落とす
4. それでも足りない場合だけ Gemini に cell情報を出させる案を検討する

## 受け入れ条件

- XLSX由来の source_ref で、該当sheet/cellへ移動できる。
- 同じ値が複数セルにある場合でも、最初に見つかった箇所へ無条件に飛ばない。
- XLSX preview の読みやすさを壊さない。

## リスク

- merged cell で cell address と見た目がずれる
- 同じ値が複数セルにあると quote だけでは決まらない
- sheet名が変わると保存済み anchor が効かなくなる
- Gemini に cell address を返させると schema と prompt が重くなる

## 削除・整理候補

- XLSXをPDF bboxと同じ概念で説明している記述
- XLSXで最初に見つかった text node だけを正とする説明
