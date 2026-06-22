# Source Ref / Bbox / Anchor Roadmap

## 目的

backend の証跡情報と bbox / highlight / anchor の精度を上げるための設計置き場。

初期ゴールは、AI抽出結果を人間がレビューしやすい状態にすること。最初から厳密な精度スコアを作るのではなく、証跡構造、PDF bbox、Office anchor、scope分割を順に整理する。

このディレクトリは、抽出値そのものよりも「その値が原本のどこにあるか」を扱う。

```text
AI抽出値
  |
  `-- source_ref
        |
        +-- document_id
        +-- page
        +-- text_quote
        +-- PDF bbox
        +-- XLSX sheet/cell
        `-- DOCX paragraph/table cell
```

## 基本方針

- Gemini raw response は `source` 文字列から `source_ref` dict へ寄せる。
- Gemini に複数 `source_refs[]` を直接返させない。MVPでは primary evidence 1件を扱う。
- Firestore / UI 互換のため、保存側の `field_metadata.source_refs[]` は当面維持する。
- document routing は後回し。先に scope 分割と schema / prompt / merge 境界を安定させる。
- bbox 失敗は抽出失敗にしない。レビュー画面で確認できる状態を優先する。
- retry loop は最後に入れる。人手編集を自動上書きしない。
- anchor resolver では `text_quote` 単独で場所を決めない。`field_path`、抽出値、文書構造、周辺ラベルも使う。

## 読む順番

まずは次の順に読む。

| 順番 | doc | 目的 |
|---:|---|---|
| 1 | [09_bbox_display_current_behavior.md](09_bbox_display_current_behavior.md) | 現在、証跡クリック時に何が光るかを理解する |
| 2 | [01_source_ref_dict.md](01_source_ref_dict.md) | `source_ref` の保存形式を理解する |
| 3 | [02_pdf_bbox.md](02_pdf_bbox.md) | PDF bbox の付与と fallback を理解する |
| 4 | [04_xlsx_cell_anchor.md](04_xlsx_cell_anchor.md) | XLSX cell anchor の実装計画を見る |
| 5 | [05_docx_block_anchor.md](05_docx_block_anchor.md) | DOCX block/cell anchor の実装計画を見る |
| 6 | [03_scoped_gemini_input.md](03_scoped_gemini_input.md) | scope別抽出の前提を見る |
| 7 | [07_document_routing.md](07_document_routing.md) | scope別に渡す書類を絞る設計を見る |
| 8 | [08_retry_loop.md](08_retry_loop.md) | bbox/scope retry と人手編集保護を見る |

## docs分類

source_ref / bbox / anchor の現役設計だけをこの階層に残す。

### 現役設計

| doc | 位置づけ |
|---|---|
| [01_source_ref_dict.md](01_source_ref_dict.md) | Gemini raw response を `{ value, source_ref }` にする設計。実装済み |
| [02_pdf_bbox.md](02_pdf_bbox.md) | PDF source_ref に bbox を付ける設計。実装済み部分あり |
| [03_scoped_gemini_input.md](03_scoped_gemini_input.md) | scope別 Gemini 入力の設計。実装済み部分あり |
| [04_xlsx_cell_anchor.md](04_xlsx_cell_anchor.md) | XLSXを sheet/cell 単位で確認する計画 |
| [05_docx_block_anchor.md](05_docx_block_anchor.md) | DOCXを paragraph/table cell 単位で確認する計画 |
| [07_document_routing.md](07_document_routing.md) | scopeごとに必要書類を渡すrouting計画 |
| [08_retry_loop.md](08_retry_loop.md) | bbox retry / scope retry の計画 |
| [09_bbox_display_current_behavior.md](09_bbox_display_current_behavior.md) | 現状調査と anchor resolver 方針更新 |

### 移動済み

Eval 系は [../008_eval_workflow/](../008_eval_workflow/) に移動済み。このディレクトリには移動済みstubを残さない。

## 将来の整理候補

次に整理するなら、次の順が安全。

| 優先 | 整理案 | 理由 |
|---:|---|---|
| 1 | `09_bbox_display_current_behavior.md` を「現状整理」と「anchor resolver方針」に分ける | 985行あり、読む負荷が高い |
| 2 | `04_xlsx_cell_anchor.md` と `05_docx_block_anchor.md` を `Office anchor` として統合する | 実装者が同じ文脈で読むため |
| 3 | `03_scoped_gemini_input.md` と `07_document_routing.md` を統合する | scope入力とroutingは実装境界が近い |

## 現状の重要ポイント

実装前の Gemini raw response は、各 field の証跡を次の文字列で返していた。

```json
{
  "value": "AMIT TAMANG",
  "source": "doc_abc123|1|AMIT TAMANG|0.95"
}
```

現在は Gemini raw response を `{ value, source_ref }` に変更し、backend が `field_metadata.source_refs[]` に変換している。旧 `source` 文字列、旧 raw `source_refs[]`、旧 `field_metadata` 別出しレスポンスの互換処理は削除済み。

この方式は Gemini response schema を軽くするためには有効だったが、次の問題がある。

- `document_id`, `page`, `text_quote`, `confidence` の意味が文字列に埋もれる
- `text_quote` に区切り文字が入ると壊れやすい
- XLSX の sheet/cell や DOCX の paragraph 情報を足しにくい
- PDF bbox、Office highlight、画像 bbox を同じ考え方で扱いにくい
- 実装を読む人にとって、Gemini 出力と保存形式の差が分かりにくい

## 調査した対象ファイル

| ファイル | 現状の役割 |
|---|---|
| `backend/extractors/schema.py` | Gemini response_schema。現在は `{ value, source_ref }` と新scope schema |
| `backend/extractors/prompt_template.py` | 通常 / scoped prompt。`source_ref` dict と新scope指示を定義 |
| `backend/extractors/gemini.py` | Gemini呼び出し、scope並列実行、deep merge、`source_ref` の正規化 |
| `backend/extractors/gemini_pipeline.py` | 書類準備済みデータから Gemini contents を作り、scope抽出と bbox を接続 |
| `backend/extractors/document_preprocessor.py` | 拡張子別に PDF / text / image へ振り分け |
| `backend/extractors/document_models.py` | `LoadedDocument`, `PreparedDocuments` の最小データ構造 |

## 初期対象外

- 最初から厳密な精度スコアを出す
- 全fieldにbboxを必ず付ける
- Geminiに複数 `source_refs[]` を直接出させる
- DOCXをPDFのような座標で再現する
- document routing を最初から強く効かせる
- retry loop で人手編集を自動上書きする

## 6つのレビュー観点

| 観点 | 主に見ること |
|---|---|
| Backend schema | Gemini schema が複雑化しすぎないか、canonical path と合っているか |
| Prompt / extraction | scope責務が重複しないか、プロンプトが読みやすいか |
| Pipeline / routing | contents と manifest が一致しているか、将来routingしやすいか |
| Viewer / evidence UX | PDF, XLSX, DOCX, image の証跡ジャンプが分かりやすいか |
| QA / restricted data | PIIを守りつつ確認できるか、golden dataを後から作れるか |
| Maintainability | 互換処理をどこで消すか、重複コードを増やさないか |

## 次にやること

01〜03は実装済み。実データ1件で Gemini schema error、PDF bbox、scope別抽出時間を確認した。

次の実装検討は anchor resolver / Office anchor。

特に重要な方針は次。

- `text_quote` 単独で場所を決めない。
- XLSX は最終的に `sheet_name + cell` へ解決する。
- DOCX は最終的に `paragraph_index` または `table_index + row + col` へ解決する。
- PDF は bbox / word bbox / Gemini bbox を使うが、bbox失敗で抽出失敗にしない。
- 複数候補を最初の1件に自動確定しない。

## QA状況

実行済み:

- `visa-app/backend` で `.venv/bin/python -m pytest -q`
- 結果: 108 passed
- 実データ1件での Gemini 抽出
- 実データ1件での schema error / timeout / bbox確認
- local frontend の案件一覧・レビュー画面・PDF bbox表示確認
- `visa-app/frontend` で `npm run build`

未実行:

- Cloud Run deploy後の動作確認
