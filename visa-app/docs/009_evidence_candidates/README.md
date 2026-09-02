# 009: 根拠位置の複数表示

Status: Part A/B 実装済み / Part D 廃止 / Part E 実装済み（2026-09-01）

## 目的

レビューの核心は「どの書類のどの記載を根拠に、この値になったか」を人が確認できること。

今回の方針では、原本に直接記載された値を抽出する時点で Gemini に根拠位置も同一応答で返させる。推測・計算・既定値には位置を付けない。Gemini APIのschema制約により、位置情報は各FieldValue内ではなくscope直下の `source_locations[]` に分離する。backend はその位置が原本上に表示できるかだけを検証し、文字一致や意味推測で別の場所を選ばない。

## ユーザー決定: UI表示方針

2026-09-01 決定。`anchor.status` は内部処理、ログ、QA集計のための状態であり、レビューUIには `resolved` / `ambiguous` / `not_found` / 未確認候補のような確認状態として露出させない。

人は「項目をクリックすると根拠位置に移動し、原本を見て自然に確認する」体験にする。複数位置がある場合も、必要な移動操作だけを提供し、内部状態名をバッジやラベルとして表示しない。

この決定は、値候補 `alternatives` の表示とは別物。値そのものが食い違う場合の「別候補」は、人が比較・採用するために表示してよい。

## データ形状

case_data の各末端フィールドは、Gemini raw response では従来どおり値と根拠quoteだけを持つ。

```json
{
  "value": "TANAKA TARO",
  "source_ref": {
    "document_id": "doc_passport",
    "page": 1,
    "text_quote": "TANAKA TARO",
    "confidence": 0.95
  }
}
```

値が食い違う候補がある場合だけ、同じ形の `alternatives` を最大2件まで付ける。値が一致している場合や候補が1つだけの場合は省略する。

Gemini response schemaを不必要に複雑にしないため、`origin` はGeminiに返させない。backendが、有効な `source_ref` を `document`、有効な証跡のない推測・計算・既定値を `derived` として付与する。`setting` / `human` は組織設定・人手編集の後段処理だけで付与する。

根拠位置はscope直下に `source_locations[]` として返す。

```json
{
  "source_locations": [
    {
      "field_path": "applicant.name_roman",
      "alternative_index": -1,
      "type": "pdf_bbox",
      "page": 1,
      "bbox": { "y_min": 120, "x_min": 100, "y_max": 160, "x_max": 420 }
    },
    {
      "field_path": "employment.monthly_salary",
      "alternative_index": 0,
      "type": "xlsx_cell",
      "anchor_id": "Sheet1!B2"
    }
  ]
}
```

`alternative_index` はprimary valueで `-1`、`alternatives[]` では0始まりのindexとする。

## locations

`source_locations[]` はviewerが直接表示するための位置情報。

- PDF / 画像PDF: `{"type": "pdf_bbox", "page": 1, "bbox": {"y_min": 120, "x_min": 100, "y_max": 160, "x_max": 420}}`
- XLSX: `{"type": "xlsx_cell", "anchor_id": "Sheet1!B2"}`
- DOCX paragraph: `{"type": "docx_block", "anchor_id": "p-0"}`
- DOCX table cell: `{"type": "docx_block", "anchor_id": "t-0-r-0-c-1"}`

Office書類では、Gemini に渡す抽出テキストへ同じIDを埋め込む。

- XLSX: `[Sheet1!B2] 260000`
- DOCX paragraph: `[p-0] TANAKA TARO`
- DOCX table cell: `[t-0-r-0-c-1] 2026-04-01`

## backend の責務

backend は `source_locations[]` を `field_path` / `alternative_index` で該当 `source_ref` に単純結合し、従来UI互換の `source_ref.anchor` に変換する。

- `xlsx_cell` / `docx_block`: 同じ `document_id` のindexに `anchor_id` が実在するかだけを見る
- `pdf_bbox`: 同じ `document_id` のPDFに対象pageが実在し、bboxが0-1000範囲で表示可能かだけを見る
- 複数の有効locationがある場合は `anchor.status = "ambiguous"` とし、有効候補を `anchor.candidates` に保持する
- 新形式で無効location、または該当fieldのlocationが返らなかった場合は `anchor.status = "not_found"` とする
- 保存済みデータ互換のため、既存の top-level `bbox` は表示用 `anchor` へ同期する
- scope直下 `source_locations[]` がない保存済みデータは、既存anchorを保持して新しい位置を推測しない

backend は次のことをしない。

- `text_quote` 文字一致で別位置を探す
- セルや段落の意味をbackendで推測する
- 後段の追加Gemini APIでbboxやセルを補完する

`anchor_coverage` の母数は、主値または別候補に値がある `origin: document` のフィールドだけとする。`derived` / `setting` / `human` と、値が見つからなかった空フィールドは母数に含めない。

## frontend の責務

レビューUIは `source_ref.anchor` を使って根拠位置へ移動する。

- PDF: 内部statusを見て表示位置を選び、bboxを強調表示する。複数位置がある場合はすべてを表示し、必要な移動操作を提供する
- XLSX / DOCX: 内部statusを見て表示位置を選び、対応する `data-anchor` 要素を強調表示する。複数位置がある場合はすべてを表示し、必要な移動操作を提供する
- 値候補 `alternatives` は「別候補N」として展開し、候補の証跡へ移動または値を採用できる
- `resolved` / `ambiguous` / `not_found` / 未確認候補といった内部状態名は、フィールド行・ビューア上の通常UIには表示しない

## 廃止した経路

Part Eで「抽出時にlocationも返す」方式へ統合したため、以下は削除した。

- `backend/extractors/bbox_locator.py`
- `backend/extractors/cell_selector.py`
- 追加Gemini APIによる後段の位置補完
- 新規抽出に対する文字一致anchor resolver

## 実装箇所

| ファイル | 内容 |
|---|---|
| `backend/extractors/schema.py` | FieldValue schema とscope直下 `source_locations[]` schema |
| `backend/extractors/prompt_template.py` | PDF/XLSX/DOCX共通のlocation出力指示 |
| `backend/extractors/gemini.py` | Gemini raw responseの正規化、origin付与、source_locations結合、alternatives保持 |
| `backend/extractors/xlsx.py` | セルID付き抽出テキストとcell index |
| `backend/extractors/docx_text.py` | 段落・表セルID付き抽出テキストとblock index |
| `backend/extractors/anchor_resolver.py` | explicit locationsの検証とanchor変換 |
| `frontend/src/components/viewer/PdfViewer.tsx` | PDF bbox表示と候補移動 |
| `frontend/src/components/viewer/HtmlViewer.tsx` | XLSX/DOCX anchor表示と候補移動 |
| `frontend/src/components/review/FieldRow.tsx` | 値候補展開、証跡移動 |

## QA観点

- 値がある `source_ref` に対応する `source_locations[]` が結合される
- 無効なlocationで文字一致fallbackが走らず `not_found` になる
- PDF bboxのpage範囲外、座標範囲外が `not_found` になる
- XLSX/DOCXの存在するanchor_idだけがresolvedになる
- primary refsだけでなく alternatives refs も同じようにanchor変換される
- 保存済みtop-level `bbox` は引き続き表示できる
- PDF/XLSX/DOCXそれぞれで複数位置がある場合に根拠位置へ移動できる
- 内部status名や「未確認候補」ラベルが通常UIに表示されない
