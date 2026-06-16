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

## 方針更新: anchor resolver では text_quote 単独に依存しない

ここから下は、上の現状整理に対する方針更新。既存の個別設計ドキュメントを直接書き換えるのではなく、anchor resolver を実装する時に採用したい新しい考え方として整理する。

anchor方式では、Geminiが返した `document_id`, `page`, `text_quote` だけで場所を決めない。`text_quote` はあくまで候補を探すための材料で、最終的な場所特定は resolver が `field_path`、抽出値、文書種別、文書構造、周辺ラベルを組み合わせて行う。

「どの形式なら何を表示するか」より大事なのは、resolver がどの手がかりで誤一致を減らすか。

| 方針 | 使う情報 | 効く形式 | 精度が上がる理由 | メリット | デメリット/注意 | MVP判断 |
|---|---|---|---|---|---|---|
| `text_quote` 単独検索 | `text_quote` | 全形式 | 精度は上がらない。既存fallbackとしてだけ使う | 実装が軽い | 重複、表記ゆれ、短すぎる値に弱い。誤ハイライトが起きる | 不採用。fallbackのみ |
| 文書を先に固定する | `document_id`, document role | 全形式 | 同じ氏名・会社名が複数文書に出ても、対象文書外を候補から外せる | 実装が軽い。誤一致を大きく減らせる | document role が未整備だと効きが弱い | 必須 |
| ページを先に固定する | `page` | PDF | PDF内の別ページにある同じ値を候補から外せる | 既存 `source_ref.page` を使える | Geminiのpageが誤ると候補を落とす | PDFでは必須 |
| `text_quote` と `locator_text` を分ける | `text_quote`, `locator_text` | 全形式 | 人間に見せる引用と、機械が探す短い語を分けられる | 長文quoteや改行差分に強い | `locator_text` が短すぎると重複する | 必須 |
| 抽出値を正規化して照合する | 抽出値、表示値、raw値 | 全形式 | `260,000円` / `260000` / `260 000` を同じ候補として扱える | 表記ゆれに強い | 正規化しすぎると別の値も一致する | 必須 |
| `field_path` で値の意味を使う | `field_path`, 値の型 | 全形式 | `260000` が給与なのか年収なのかを区別できる | 非エンジニアにも説明しやすい | field名と文書ラベルの対応表が必要 | 必須 |
| 項目ラベルで絞る | `label_text`, 近くのラベル | 全形式 | `基本給` の近くの `260000` のように、値の意味で候補を絞れる | 重複値に強い | ラベル表記ゆれがある | MVPで採用 |
| 前後文脈で絞る | `context_before`, `context_after`, 見出し | PDF/DOCX | 同じ値でも、周辺文から正しい箇所を選びやすい | ルール化しやすい | 文脈をどこまで見るか決める必要がある | MVPでは短く採用 |
| XLSX構造で絞る | `sheet_name`, `cell`, `row`, `col`, 左/上セル, 列見出し | XLSX | Excelのセル位置と行列ラベルを使える | 文字検索より安定する | merged cell や数式表示に注意 | 必須 |
| DOCX構造で絞る | `paragraph_index`, `table_index`, `row`, `col`, 見出し, 表ラベル | DOCX | 段落・表セルを区別できる | PDF bboxより実装が軽い | Wordの見た目のページとは一致しない | 必須 |
| PDF text-layer word bboxを使う | PDF内単語bbox、page、値、ラベル | PDFテキスト層あり | LLMに聞かず、PDFが持つ単語座標からbboxを作れる | 速い、安い、決定的 | スキャンPDFでは効かない | PDFでは優先 |
| OCR word bboxを使う | OCR単語bbox、値、ラベル | スキャンPDF | テキスト層がないPDFでも座標を作れる | スキャンに強い | OCRコストと誤認識がある | 後続候補 |
| Gemini bboxを主要項目だけに使う | page画像、`locator_text`, `field_path`, ラベル | PDF | テキスト層やOCRで難しい場合に画像から位置を聞ける | スキャンにも使える | コスト高め。不安定さがある | `PDF_BBOX_TARGET_FIELDS` 限定で採用 |
| candidate idでLLM応答を対応づける | `candidate_id`, `ref_index`, `field_path`, `page`, `locator_text` | PDF/Gemini bbox | 複数source_refを一括で処理しても、返答と元候補が混線しにくい | 既存の後付けbbox処理と相性がよい | 永続保存するとsource_refが複雑になる | resolver内部だけ採用 |
| 複数候補ならanchorを付けない | `match_count`, `anchor_status` | 全形式 | 誤った場所を確定表示しない | 信頼性が上がる | 光らない項目が残る | 必須 |
| fallback表示を弱く見せる | `anchor_status` | 全形式 | 文字検索結果を確定証跡と誤認させない | レビュー時の誤解が減る | UI表示の種類が増える | MVPで採用 |
| 複数候補UIを出す | `anchor_candidates` | 全形式 | 人間が候補から選べる | 誤確定を避けられる | UIと保存設計が重い | 後回し |
| LLMにセル番地/段落番号を返させる | LLM出力 | XLSX/DOCX | resolver実装が軽く見える | 実際には位置番号を間違えやすい | prompt/schemaが重くなる | 初期は非推奨 |

MVPの基本方針は、`text_quote` を賢くすることではなく、`text_quote` を候補検索語の1つに下げること。

```text
text_quoteだけで探す
  |
  v
誤一致しやすい


anchor resolverで探す
  |
  |-- document_id / page で範囲を絞る
  |-- field_path / 値の型で意味を絞る
  |-- locator_text / 正規化値で候補を作る
  |-- ラベル / 周辺文脈 / 構造で一意化する
  |
  v
一意なら anchor を付ける
複数なら anchor を付けない
```

`source_ref` は、次の4層で考えると分かりやすい。

```text
source_ref
  |
  |-- 1. 原本識別
  |     document_id, page
  |
  |-- 2. 人間に見せる根拠
  |     text_quote
  |
  |-- 3. resolver用ヒント
  |     locator_text, label_text, context_before, context_after
  |
  `-- 4. 解決済みanchor
        anchor_type, bbox, sheet_name, cell, paragraph_index, table_index, row, col
```

`text_quote` は「根拠として引用された文字列」。`locator_text` は「resolverが実際に探す短い文字列」。`label_text` や `context_before/after` は「同じ値が複数ある時に、どれが本命かを見分ける文脈」。

保存する情報と、保存しない情報も分けておく。

| 分類 | 情報 | 理由 |
|---|---|---|
| 保存する | `anchor_type` | viewer が形式別に表示方法を選ぶため |
| 保存する | `locator_text` | `text_quote` が長い/揺れる場合でも、resolverやfallbackで使いやすいため |
| 保存する | `label_text` | 同じ値が複数ある時に、人間にもなぜそこを選んだか説明しやすいため |
| 保存する | PDFの `bbox` | PDFで実際に光らせる場所そのもの |
| 保存する | XLSXの `sheet_name`, `cell`, `row`, `col` | セルへ直接ジャンプするため |
| 保存する | DOCXの `paragraph_index`, `table_index`, `row`, `col` | 段落または表セルへ直接ジャンプするため |
| 保存してもよい | `anchor_status`, `match_count` | UI/QAで「特定済み」「曖昧」「未検出」を区別しやすい |
| 基本保存しない | `anchor_candidates[]` | source_ref が重くなる。MVPでは一意でなければ anchor なしでよい |
| 基本保存しない | `candidate_id` | Gemini bboxなどの内部対応づけ用。永続化する必要は薄い |
| 基本保存しない | 正規化済みquote | resolver内で再計算できる |
| 保存しない | CSS selector / XPath / DOM selector | preview HTMLの実装詳細に依存し、壊れやすい |

## text_quote 検索の位置づけ

`text_quote` 検索は残す。ただし、場所特定の主役にはしない。

現状の `text_quote` 検索は「同じ文字列を文書内で探し、最初に見つかった場所を光らせる」方式に近い。これは軽くて便利だが、原本確認の根拠としては弱い。

特に次の値は、同じ文書内に何度も出やすい。

| 値の種類 | リスク |
|---|---|
| 氏名 | 履歴書、旅券、雇用契約書、申請書に何度も出る |
| 会社名 | 契約書、会社概要、申請書に何度も出る |
| 給与 | 基本給、月額、年収、手当、控除欄で重複しやすい |
| 日付 | 生年月日、入社日、卒業日、契約開始日が混ざる |
| はい/いいえ | `有` / `無` / `Yes` / `No` は文書内に多数出る |
| 国籍・住所 | 表記ゆれ、改行、スペース差分が多い |

一番避けたいのは、ハイライトできないことより、誤った場所を正しそうにハイライトすること。

```text
基本給        260000
月額合計      260000
控除後支給額  260000

source_ref.text_quote = "260000"
        |
        v
最初に見つかった 260000 を光らせる
        |
        v
それが「基本給」の根拠とは限らない
```

そのため、`text_quote` は「場所そのもの」ではなく、anchor resolver が場所を探すための手がかりの1つとして扱う。

```text
今の考え方

text_quote
  |
  v
場所を直接探す


推奨する考え方

field_path + value + document_id + page + text_quote + 文書構造
  |
  v
anchor resolver が候補を絞り込む
  |
  v
PDF bbox / XLSX cell / DOCX block に変換する
```

## anchor resolver は text_quote だけで解決しない

anchor resolver の精度を上げるには、`text_quote` だけで候補を探さないことが重要。

`text_quote` はLLMが返した引用文字列なので、次の弱さがある。

- 同じ値が複数箇所に出る。
- `260,000` と `260000` のような表記ゆれがある。
- 長すぎる quote は途中改行や空白差分で一致しない。
- 短すぎる quote は別の箇所にも一致する。
- `有` / `無` / `Yes` / `No` のような値は文書内に大量に出る。

そのため、resolver は次の情報を組み合わせて候補を絞る。

| 情報 | 役割 | 保存先/取得元 | 例 |
|---|---|---|---|
| `document_id` | どの文書から探すかを固定する | `source_ref` | `doc_employment_terms` |
| `page` | PDFの対象ページを絞る | `source_ref` | `1` |
| `field_path` | 何の項目を探しているかを知る | `field_metadata` のキー | `employment.monthly_salary` |
| 抽出値 | quoteではなく正規化済みの値として照合する | `case_data` / `field_metadata.original_value` | `260000` |
| `text_quote` | 候補検索の文字列手がかり | `source_ref` | `260,000円` |
| `locator_text` | bbox/OCR向けの短い検索語 | resolver内部で作る | `260,000` |
| 文書種別 / role | 履歴書、雇用条件通知書、会社資料などの優先度に使う | document manifest | `employment_terms` |
| XLSX構造 | sheet/cell/row/col で候補を絞る | `extract_xlsx_cells()` | `Sheet1!B12` |
| DOCX構造 | paragraph/table/row/col で候補を絞る | `extract_docx_blocks()` | `table=0,row=3,col=1` |
| 周辺ラベル | 同じ値が複数ある時の補助材料 | resolver内部の文書index | `基本給`, `月額報酬` |

非エンジニア向けに言うと、`text_quote` だけで探すのは「260000という文字だけで探す」こと。anchor resolver では「給与という項目で、雇用条件通知書の中にあり、基本給ラベルの近くにある260000」を探す。

```text
弱い探し方

260000 を探す
  |
  +-- 基本給 260000
  +-- 月額合計 260000
  `-- 控除後 260000


強い探し方

field_path = employment.monthly_salary
document_role = employment_terms
nearby_label = 基本給 / 月額報酬
value = 260000
  |
  v
基本給 260000 を優先候補にする
```

初期実装では、すべてをLLMに返させる必要はない。Geminiには従来どおり `source_ref` を返させ、resolver側が `field_path`、抽出値、文書構造index、周辺ラベルを使ってanchorを補完する。

## 精度改善方針の優先順位

上の表を、実装順に並べると次になる。

| 優先 | 方針 | 理由 |
|---|---|---|
| 1 | `document_id` / `page` / document role で探索範囲を固定する | ここがズレると後続の精度改善が効かない |
| 2 | 形式別の文書indexを作る | PDF word bbox、XLSX cell、DOCX paragraph/table cell を候補として扱えるようにする |
| 3 | `locator_text` と正規化値で候補を作る | 表記ゆれに対応しながら、`text_quote` 依存を下げる |
| 4 | `field_path` と項目ラベルでスコアリングする | 同じ値が複数ある場合の判定材料になる |
| 5 | 一意に決まる場合だけ anchor を保存する | 誤ハイライトを避ける |
| 6 | PDF主要項目だけ Gemini bbox を使う | 全項目LLM bboxは重いので、必要な項目に絞る |
| 7 | fallback表示を弱く見せる | resolver未解決なのに確定位置のように見える問題を避ける |
| 8 | 複数候補UIを検討する | MVP後に、人間の確認で補えるようにする |

## 推奨する場所特定の優先順位

場所特定は、強い情報から順に使う。

```text
1. 構造anchor
   PDF  -> bbox
   XLSX -> sheet_name + cell
   DOCX -> paragraph_index / table_index + row + col

2. PDF text-layer / OCR word bbox
   field_path / value / text_quote を手がかりに、単語座標から bbox を作る

3. Gemini bbox
   PDF_BBOX_TARGET_FIELDS の主要項目だけ、field_path / locator_text / 周辺文脈を渡して bbox を取得する

4. text_quote fallback
   一意に見つかった場合だけ暫定ハイライトする

5. 複数一致
   最初の1件に自動ジャンプしない
```

形式別に見ると、次の考え方になる。

| 形式 | 主役にする方式 | `text_quote` の役割 |
|---|---|---|
| PDF テキスト層あり | word bbox / bbox | 候補検索語の1つ。`field_path` / value / page と合わせる |
| PDF スキャン画像 | OCR word bbox / Gemini bbox | OCR/Gemini bboxへの検索語の1つ。`locator_text` として短くする |
| XLSX | `sheet_name + cell` | セル候補検索語の1つ。sheet/cell/周辺ラベルと合わせる |
| DOCX 段落 | `paragraph_index` | 段落候補検索語の1つ。field_path/見出し/周辺文脈と合わせる |
| DOCX 表セル | `table_index + row + col` | 表セル候補検索語の1つ。行/列ラベルと合わせる |

## MVPでの現実的な絞り込みルール

最初から複雑な推論を入れすぎない。まずは次の順で候補を絞る。

```text
1. document_id で対象文書を固定する
2. PDFは page で対象ページを固定する
3. XLSX/DOCXは文書構造indexから候補を作る
4. field_path から期待する値の種類を判断する
   - salary / jpy / count / date / name など
5. text_quote と抽出値を正規化して照合する
6. 一意に決まる場合だけ anchor を付ける
7. 複数候補なら、周辺ラベルで一段だけ絞る
8. それでも複数なら anchor を付けない
```

ここで重要なのは、複数候補を無理に1つへ決めないこと。`text_quote` だけで一意に見える場合でも、field_pathや文書構造と矛盾するならanchorを付けない。

## UIでの見せ方

`text_quote` 検索結果は、bboxやセルanchorと同じ信頼度で見せない。

| 状態 | 表示案 |
|---|---|
| PDF bboxあり | `原本位置: 特定済み` |
| XLSX cellあり | `原本位置: Sheet1!B12` |
| DOCX block/cellあり | `原本位置: 段落12` / `表1 行2 列3` |
| text_quote 一意一致 | `文字検索で表示` |
| text_quote 複数一致 | `候補が複数あります` |
| 一致なし | `原本位置を特定できません` |

`text_quote` 検索は便利な保険だが、確定証跡のように見せない。

```text
anchorあり
  -> 確定に近い証跡

text_quote 一意一致
  -> 暫定だが使える証跡

text_quote 複数一致
  -> 自動確定しない

text_quote 一致なし
  -> 証跡位置未特定
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
