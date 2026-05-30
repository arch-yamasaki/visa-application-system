# Source Ref / Bbox Improvement Roadmap

## 目的

backend の証跡情報と bbox / highlight の精度を上げるための大枠作業計画。

初期ゴールは、AI抽出結果を人間がレビューしやすい状態にすること。最初から厳密な精度スコアを作るのではなく、証跡構造、PDF bbox、Office anchor、scope分割を順に整理する。

## 基本方針

- Gemini raw response は `source` 文字列から `source_ref` dict へ寄せる。
- Gemini に複数 `source_refs[]` を直接返させない。MVPでは primary evidence 1件を扱う。
- Firestore / UI 互換のため、保存側の `field_metadata.source_refs[]` は当面維持する。
- document routing は後回し。先に scope 分割と schema / prompt / merge 境界を安定させる。
- bbox 失敗は抽出失敗にしない。レビュー画面で確認できる状態を優先する。
- retry loop は最後に入れる。人手編集を自動上書きしない。

## 優先順位

| 順番 | 計画 | 詳細 |
|---:|---|---|
| 1 | `source_ref` dict 化 | [01_source_ref_dict.md](01_source_ref_dict.md) |
| 2 | PDF bbox 改善 | [02_pdf_bbox.md](02_pdf_bbox.md) |
| 3 | scope 別 Gemini 入力 | [03_scoped_gemini_input.md](03_scoped_gemini_input.md) |
| 4 | XLSX cell anchor | [04_xlsx_cell_anchor.md](04_xlsx_cell_anchor.md) |
| 5 | DOCX block anchor | [05_docx_block_anchor.md](05_docx_block_anchor.md) |
| 6 | Golden data 評価 | [06_golden_data_evaluation.md](06_golden_data_evaluation.md) |
| 7 | document routing 実装 | [07_document_routing.md](07_document_routing.md) |
| 8 | bbox retry / scope retry loop | [08_retry_loop.md](08_retry_loop.md) |
| 9 | 取次者 autofill bug | [09_intermediary_autofill_bug.md](09_intermediary_autofill_bug.md) |
| 10 | Eval golden canonical v2 移行 | [10_eval_golden_canonical_v2_plan.md](10_eval_golden_canonical_v2_plan.md) |
| 11 | Golden data 確認ワークフロー | [11_golden_data_review_workflow.md](11_golden_data_review_workflow.md) |

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

その後、04 XLSX cell anchor に進む。

## QA状況

実行済み:

- `visa-app/backend` で `.venv/bin/python -m pytest -q`
- 結果: 108 passed
- 実データ1件での Gemini 抽出
- 実データ1件での schema error / timeout / bbox確認
- local frontend の案件一覧・レビュー画面・PDF bbox表示確認
- `visa-app/frontend` で `npm run build`
- 詳細: [QA_REAL_DATA_2026-05-31.md](QA_REAL_DATA_2026-05-31.md)

未実行:

- Cloud Run deploy後の動作確認
- Chrome拡張の取次者入力バグ修正。詳細は [09_intermediary_autofill_bug.md](09_intermediary_autofill_bug.md)
