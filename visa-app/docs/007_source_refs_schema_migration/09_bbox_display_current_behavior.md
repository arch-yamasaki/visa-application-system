# 09 bbox / highlight の現状整理

Status: 調査メモ

## このメモの目的

レビュー画面で「証跡をクリックしたときに、原本のどこが光るのか」を整理する。

特に、次の疑問に答えるためのメモ。

- PDF の bbox はどう付くのか
- PDF でも bbox が付く場合と付かない場合は何が違うのか
- PDF にテキストがある場合はどう表示されるのか
- DOCX / XLSX は bbox が付くのか
- どの分岐で、表示される / 表示されないが決まるのか

## まず全体像

現在の証跡は、基本的に `field_metadata.source_refs[]` に保存される。

```json
{
  "document_id": "doc_xxx",
  "page": 1,
  "text_quote": "AMIT TAMANG",
  "confidence": 0.9
}
```

PDF だけ、後処理で `bbox` が付くことがある。

```json
{
  "document_id": "doc_pdf_1",
  "page": 1,
  "text_quote": "AMIT TAMANG",
  "confidence": 0.9,
  "bbox": {
    "y_min": 100,
    "x_min": 200,
    "y_max": 130,
    "x_max": 260
  }
}
```

非エンジニア向けに言うと、`source_ref` は「原本のどの文書・どのページ・どの文字列か」を表すメモで、`bbox` は「その文字列が紙面のどの四角い範囲にあるか」を表す追加メモ。

```text
field_metadata
  |
  v
source_ref
  |
  |-- document_id  どの文書か
  |-- page         何ページか
  |-- text_quote   どの文字を探すか
  |-- confidence   抽出の自信度
  |
  `-- bbox         PDF上の四角い場所。付く場合と付かない場合がある
```

レビュー画面のクリックから表示までは、次の流れ。

```text
レビュー項目をクリック
        |
        v
FieldRow
        |
        | source_refs[0] だけを使う
        v
viewerStore.navigateToSource()
        |
        | currentDocumentId
        | currentPage
        | highlightText = text_quote
        | highlightSourceRef = source_ref 全体
        v
DocumentViewer
        |
        | ファイル拡張子で分岐
        |
        +-- .pdf --------------> PdfViewer
        |
        +-- .docx / .xlsx -----> HtmlViewer
        |
        `-- 画像 --------------> ImageViewer
```

主な参照:

- `frontend/src/components/review/FieldRow.tsx`
- `frontend/src/store/viewerStore.ts`
- `frontend/src/components/viewer/DocumentViewer.tsx`

## PDF の bbox はどう付くか

PDF の bbox は、Gemini の通常抽出結果に最初から入っているわけではない。

流れは次の通り。

```text
PDFアップロード
        |
        v
document_preprocessor.prepare_documents()
        |
        | PDF bytes を prepared.pdf_contents に入れる
        | document_id -> PDF bytes を pdf_bytes_map に保存する
        v
Gemini 抽出
        |
        | PDFそのものをGeminiに渡す
        | 値と source_ref を抽出する
        | ここでは bbox はまだない
        v
gemini_pipeline.attach_bboxes()
        |
        v
bbox_locator.locate_bboxes()
        |
        | 1. bbox対象フィールドだけ候補にする
        | 2. 候補を document_id + page ごとにまとめる
        | 3. PDFページを画像に変換する
        | 4. 画像と text_quote をGeminiに渡す
        | 5. Geminiから座標を受け取る
        v
field_metadata.source_refs[].bbox に後付けする
```

イメージとしては、通常の抽出AIに「この人の名前は何ですか」と聞いたあと、別の処理で「その名前は紙面のどこにありますか」と聞き直している。

```text
1回目のGemini
  Q: このPDFから申請人名を抽出して
  A: AMIT TAMANG。証跡は doc_pdf_1 の1ページ目の "AMIT TAMANG"

2回目のGemini bbox
  Q: このページ画像の中で "AMIT TAMANG" はどこ？
  A: 上から100、左から200、下130、右260あたり
```

関連ファイル:

- `backend/extractors/document_preprocessor.py`
- `backend/extractors/gemini_pipeline.py`
- `backend/extractors/bbox_locator.py`
- `backend/extractors/gemini.py`

## PDF でも bbox が付く条件

PDF で bbox が付くには、少なくとも次の条件を満たす必要がある。

```text
PDFである
  |
  v
attach_bbox_refs が有効
  |
  v
ENABLE_BBOX_LOCATOR が false ではない
  |
  v
field_path が BBOX_TARGET_FIELDS に入っている
  |
  v
source_ref に document_id がある
  |
  v
source_ref に text_quote がある
  |
  v
document_id が pdf_bytes_map に存在する
  |
  v
page がPDFの範囲内
  |
  v
PDFページを画像化できる
  |
  v
Gemini bbox が4つの座標を返す
  |
  v
bbox が保存される
```

この中で特に重要なのは `BBOX_TARGET_FIELDS`。

現在は「レビュー画面にあるすべての項目」ではなく、`backend/extractors/bbox_locator.py` の `BBOX_TARGET_FIELDS` に書かれた項目だけが bbox 付与対象になる。

```text
レビュー画面の項目
  |
  |-- applicant.name_roman
  |-- applicant.sex
  |-- employment.monthly_salary
  |-- employer.name
  |-- ...
  |
  v
BBOX_TARGET_FIELDS に入っている？
  |
  +-- YES -> bbox候補になる
  |
  `-- NO  -> PDFでもbbox候補にならない
```

つまり、PDFで正しい `source_ref` があっても、その項目が `BBOX_TARGET_FIELDS` に入っていなければ bbox は付かない。

## PDF でも bbox が付かない主なケース

```text
PDFなのにbboxがない
  |
  +-- bbox locator が無効
  |
  +-- field_path が BBOX_TARGET_FIELDS にない
  |
  +-- source_ref がない
  |
  +-- source_ref.document_id が空
  |
  +-- source_ref.text_quote が空
  |
  +-- document_id が PDF として保持されていない
  |
  +-- page が存在しない
  |
  +-- PDFページの画像化に失敗
  |
  +-- Gemini bbox が見つけられなかった
  |
  `-- Gemini bbox の返答形式が不正
```

ここで大事なのは、`bbox がない = 証跡がない` ではないこと。

`bbox` がなくても、`document_id`, `page`, `text_quote` があれば、フロント側で文字検索ハイライトに落ちる可能性がある。

## PDF の表示分岐

PDFビューア側の表示は、次の優先順位。

```text
PdfViewer
  |
  v
sourceRef.bbox がある？
  |
  +-- YES
  |     |
  |     v
  |   bbox座標で四角を描く
  |
  `-- NO
        |
        v
      highlightText がある？
        |
        +-- YES
        |     |
        |     v
        |   PDF.js の getTextContent() で text_quote を探す
        |   見つかれば文字位置に四角を描く
        |
        `-- NO
              |
              v
            ハイライトなし
```

つまりPDFには、表示方法が2種類ある。

| 表示方法 | 使う情報 | 強い場面 | 弱い場面 |
|---|---|---|---|
| bbox表示 | `source_ref.bbox` | スキャンPDFでも座標があれば表示できる | bboxが付いていないと使えない |
| text検索表示 | `text_quote` | テキスト層があるPDFなら軽く表示できる | スキャン画像PDFでは検索できないことが多い |

## PDFにテキストがある場合

PDFには大きく2種類ある。

```text
PDF
  |
  +-- テキスト層ありPDF
  |     例: Wordやシステムから出力したPDF
  |     文字を選択・コピーできる
  |
  `-- スキャン画像PDF
        例: 紙をスキャンしたPDF
        見た目は文字だが、中身は画像
```

フロントの `PdfViewer` は、bboxがない場合に PDF.js の `getTextContent()` で文字を探す。

```text
PDFにテキスト層がある
  |
  v
getTextContent() で文字が取れる
  |
  v
text_quote 検索でハイライトできる可能性がある
```

一方で、スキャン画像PDFはこうなる。

```text
スキャン画像PDF
  |
  v
getTextContent() で文字が取れない
  |
  v
text_quote 検索ではハイライトできない
  |
  v
bbox がなければ表示できない
```

注意点として、バックエンドには `pdf_text.py` があり、PyMuPDFでPDF内の単語とbboxを読む部品は存在する。ただし、現在の PDF direct + bbox 後付けの本線では、PDFテキスト層から直接 bbox を作る流れではなく、PDFページを画像化して Gemini bbox に聞く流れになっている。

## DOCX の場合

DOCXには、現在 bbox は付かない。

処理の流れは次の通り。

```text
DOCXアップロード
        |
        v
document_preprocessor.prepare_documents()
        |
        v
docx_text.extract_docx()
        |
        | 段落テキストを集める
        | 表セルのテキストを集める
        | paragraph_index / table_index / row / col は保持しない
        v
prepared.text_contents
        |
        v
Gemini 抽出
        |
        | text_contents から値と source_ref を作る
        v
field_metadata.source_refs[]
        |
        | bbox は付かない
        v
レビュー画面
```

DOCXのプレビューは、バックエンドでHTMLに変換される。

```text
DOCX
  |
  v
backend/main.py _docx_to_html()
  |
  v
HTML preview

<div>
  <p>段落テキスト</p>
  <table>
    <tr>
      <td>表セルの文字</td>
    </tr>
  </table>
</div>
```

現在のHTMLには、次のような証跡用の目印は入っていない。

```html
<p data-paragraph-index="12">...</p>
<td data-table-index="0" data-row="3" data-col="1">...</td>
```

そのため、フロントは `text_quote` を使ってHTML内を文字検索する。

```text
DOCXのレビュー項目をクリック
        |
        v
DocumentViewer が .docx と判定
        |
        v
HtmlViewer を表示
        |
        v
iframe 内のHTMLテキストを上から検索
        |
        v
最初に見つかった text_quote を <mark> する
```

限界は、同じ文字が複数ある場合。

```text
段落1: AMIT TAMANG
段落2: 申請人 AMIT TAMANG は...
表セル: 氏名 AMIT TAMANG

source_ref.text_quote = "AMIT TAMANG"
        |
        v
どの AMIT TAMANG が正しい証跡かは分からない
        |
        v
画面上で最初に見つかったものが光る
```

## XLSX の場合

XLSXにも、現在 bbox は付かない。

処理の流れは次の通り。

```text
XLSXアップロード
        |
        v
document_preprocessor.prepare_documents()
        |
        v
xlsx.extract_xlsx()
        |
        | シートごとにセルの値を読む
        | 行ごとにタブ区切りテキストにする
        | sheet_name / cell / row / col は source_ref には保持しない
        v
prepared.text_contents
        |
        v
Gemini 抽出
        |
        | text_contents から値と source_ref を作る
        v
field_metadata.source_refs[]
        |
        | bbox は付かない
        v
レビュー画面
```

XLSXのプレビューは、バックエンドでHTMLテーブルに変換される。

```text
XLSX
  |
  v
backend/main.py _xlsx_to_html()
  |
  v
HTML preview

<div>
  <h3>Sheet1</h3>
  <table>
    <tr>
      <td>基本給</td>
      <td>260000</td>
    </tr>
  </table>
</div>
```

現在のHTMLには、次のような証跡用の目印は入っていない。

```html
<td data-sheet="Sheet1" data-cell="B12" data-row="12" data-col="2">
  260000
</td>
```

そのため、DOCXと同じく `text_quote` の文字検索になる。

```text
XLSXのレビュー項目をクリック
        |
        v
DocumentViewer が .xlsx と判定
        |
        v
HtmlViewer を表示
        |
        v
iframe 内のHTMLテキストを上から検索
        |
        v
最初に見つかった text_quote を <mark> する
```

XLSXで特に問題になりやすいのは、同じ値が複数セルに出ること。

```text
Sheet1

        A列       B列
  1     基本給    260000
  2     月額合計  260000
  3     控除前    260000

source_ref.text_quote = "260000"
        |
        v
B1 / B2 / B3 のどれか分からない
        |
        v
画面上で最初に見つかったセルが光る
```

シートについても同じ。

```text
Sheet1: 260000
Sheet2: 260000

source_ref には sheet_name がない
        |
        v
どのシートの 260000 か分からない
```

## 形式別まとめ

| 形式 | bboxは付くか | 表示の第一優先 | fallback | 主な弱点 |
|---|---:|---|---|---|
| PDF | 付くことがある | bbox座標 | PDF.js text検索 | `BBOX_TARGET_FIELDS` 外はbbox対象外。スキャンPDFはtext検索が弱い |
| PDF テキスト層あり | 付くことがある | bbox座標 | PDF.js text検索 | bboxなしでも検索表示できる可能性はあるが、同じ文言には弱い |
| PDF スキャン画像 | 付くことがある | bbox座標 | ほぼ効かない | bboxがないと光らないことが多い |
| DOCX | 付かない | text_quote検索 | なし | 同じ文字が複数あると最初の一致に飛ぶ |
| XLSX | 付かない | text_quote検索 | なし | セル番地・シート名を持たないので同じ値に弱い |
| 画像 | 付かない | 画像表示のみ | なし | 現状は証跡ハイライト対象外 |

## 表示される / 表示されないを決める分岐

```text
証跡クリック
  |
  v
source_refs[0] がある？
  |
  +-- NO -> 何も移動しない
  |
  `-- YES
        |
        v
      document_id の文書を開く
        |
        v
      拡張子は？
        |
        +-- PDF
        |     |
        |     v
        |   bbox がある？
        |     |
        |     +-- YES -> bboxを表示
        |     |
        |     `-- NO
        |           |
        |           v
        |         text_quote がPDFテキスト層で見つかる？
        |           |
        |           +-- YES -> text検索ハイライト
        |           |
        |           `-- NO  -> ハイライトなし
        |
        +-- DOCX / XLSX
        |     |
        |     v
        |   HTML preview を開く
        |     |
        |     v
        |   text_quote がHTML内で見つかる？
        |     |
        |     +-- YES -> 最初の一致をハイライト
        |     |
        |     `-- NO  -> ハイライトなし
        |
        `-- 画像
              |
              v
            画像表示のみ。ハイライトなし
```

## bbox が保存されていても表示されないケース

保存済みの `bbox` があっても、フロントで表示されないことがある。

```text
bbox は保存されている
  |
  +-- field_metadata が list形式で返り、ReviewPageの正規化で bbox が落ちる
  |
  +-- bbox付きsource_ref が source_refs[0] ではなく2個目以降にある
  |
  +-- 文書拡張子が .pdf と判定されない
  |
  +-- DOCX / XLSX なので HtmlViewer に行き、bboxを使わない
  |
  +-- ユーザーがページ送りを押して highlightSourceRef がクリアされる
  |
  `-- 文書タブを直接クリックして空の source_ref で開いている
```

特に重要なのは、現在の `FieldRow` が `source_refs[0]` だけを見ること。

```text
source_refs
  |
  +-- [0] bboxなし
  |
  `-- [1] bboxあり

現在のUIは [0] だけ使う
        |
        v
bboxありの [1] は表示に使われない
```

## 現状の重要ポイント

1. bbox は PDF にだけ後付けされる。
2. PDFでも全項目にbboxが付くわけではない。
3. `BBOX_TARGET_FIELDS` にない項目は、PDFでもbbox対象外。
4. PDFの表示は `bbox優先、なければtext_quote検索`。
5. PDFのtext検索は、テキスト層があるPDFでないと弱い。
6. DOCX / XLSX は bbox ではなく、HTML preview上の `text_quote` 検索。
7. DOCX / XLSX は段落番号・表セル・シート名・セル番地を証跡として持っていない。
8. 同じ文字列が複数ある文書では、現在の `text_quote` 検索は誤った場所を光らせる可能性がある。

## anchor resolver につながる論点

現在の仕組みは、`text_quote` にかなり依存している。

```text
現在

source_ref
  |
  |-- document_id
  |-- page
  `-- text_quote
        |
        v
      文字検索で場所を探す
```

anchor resolver を入れるなら、目指す形は次。

```text
将来

source_ref
  |
  |-- document_id
  |-- page
  |-- text_quote
  |
  `-- anchor
        |
        +-- PDF  -> bbox
        |
        +-- XLSX -> sheet_name + cell
        |
        `-- DOCX -> paragraph_index / table_index + row + col
```

つまり、anchor resolver は「文字列」から「表示しやすい場所情報」へ変換する係。

```text
Gemini
  |
  | 値と text_quote を返す
  v
Anchor Resolver
  |
  | 文書構造を見て場所を補完する
  v
Viewer
  |
  | 形式に合った方法で光らせる
  v
ユーザーが原本確認できる
```

この設計にすると、Gemini にセル番地や段落番号まで無理に出させずに済む。PDF / DOCX / XLSX それぞれの表示都合は、アプリ側の resolver と viewer に閉じ込められる。

