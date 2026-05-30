# 02 PDF bbox 改善

Status: 実装済み

## 目的

PDF由来の証跡について、レビュー画面で該当箇所に安定してジャンプ・ハイライトできるようにする。

## 現状

- `backend/extractors/bbox_locator.py` が `field_metadata.source_refs[]` を読み、PDF page画像から bbox を取得する。
- `gemini_pipeline.py` の `attach_bboxes()` が抽出後に bbox を付与する。
- frontend の PDF viewer は、`bbox` があれば座標ハイライト、なければ `text_quote` fallback を使う。

## 課題

- bbox対象fieldが固定 allowlist。
- `text_quote` だけで位置を探しているため、同じ文字列が複数あるページでぶれやすい。
- 長い quote や表のセル値は bbox 検出に向かない。
- bbox付与単位が field path に寄っており、source_ref単位の考え方が弱い。

## 方針

- field 単位ではなく `source_ref` 単位で bbox を扱う。
- `text_quote` と bbox用の短い `locator_text` の役割を分ける。
- bbox prompt は field path ではなく、内部 `bbox_candidate_id` を返させる。
- 同一ページで同じ quote が複数ある場合の扱いを明確にする。
- bbox が取れなくても抽出自体は失敗にしない。

## bbox candidate

旧実装は、同じ `field_path` に複数 source_ref がある場合に混線しやすかった。

そのため、bbox探索時だけ内部IDを作る。

```json
{
  "bbox_candidate_id": "candidate_001",
  "field_path": "employment.monthly_salary",
  "ref_index": 0,
  "document_id": "doc_pdf123",
  "page": 1,
  "text_quote": "Monthly Salary 260,000 yen",
  "locator_text": "260,000"
}
```

Gemini bbox prompt には candidate list を渡し、返却も candidate ID 起点にする。

```json
{
  "candidate_001": [100, 200, 130, 260]
}
```

これにより、`field_path + document_id + page` が同じでも、source_ref単位で bbox を戻せる。

返却配列は `[y_min, x_min, y_max, x_max]` の 0-1000 正規化座標。保存時も既存UI互換の `{ y_min, x_min, y_max, x_max }` を維持する。

## 作業計画

1. `bbox_locator.py` の `BBOX_TARGET_FIELDS` を棚卸しする。
2. PDF source_ref があるのに bbox対象外になっている field を確認する。
3. `source_ref` ごとに bbox を付与する前提に整理する。
4. `bbox_candidate_id` を内部的に作る設計にする。
5. `locator_text` を導入するか決める。
6. bbox prompt に candidate ID / field path / quote / locator text / 周辺文脈を渡す設計にする。
7. bbox 結果を candidate ID から元の source_ref に戻す。
8. PDF viewer fallback との役割分担を docs に追記する。

## fallback 方針

`PdfViewer` は現状どおり、bbox があれば bbox を優先する。

bbox がない場合だけ `text_quote` fallback を使う。ただし、fallback の部分一致は誤ハイライトを生みやすい。将来的には次の方針にする。

- 完全一致または高信頼の正規化一致を優先する
- 同一ページに複数候補がある場合は、無理に1つへ決めない
- 短すぎる quote は fallback highlight しない
- fallback は「補助」であり、bboxより強い根拠にはしない

## 受け入れ条件

- PDF由来の主要fieldで bbox が付く。
- bboxがない場合も既存の text search fallback が動く。
- bbox失敗で抽出結果保存が失敗しない。
- 同じ field に複数 source_ref がある場合に bbox が混線しない。

## 後回し

- 全field bbox必須化。
- bbox正解率の厳密なスコアリング。
- 人間がbbox正解を手で作る golden dataset。

## 削除・整理候補

- `BBOX_TARGET_FIELDS` のうち review catalog と対応していない項目
- `bbox_locator.py` から `gemini.py` の内部関数へ依存している箇所
- APIが dict 形式の `field_metadata` に固定された後の list互換処理

## 実装内容

- `backend/extractors/bbox_locator.py`
  - bbox探索単位を `field_path` から内部 `candidate_id` に変更
  - candidate は `field_path`, `ref_index`, `document_id`, `page`, `text_quote`, `locator_text` を持つ
  - bbox結果は candidate ID から元の `source_refs[ref_index]` に戻す
  - `candidate_id` は保存しない
- `backend/extractors/gemini.py`
  - `get_bboxes_for_page()` を candidate ID 入力/出力に変更
- `backend/tests/test_bbox_locator.py`
  - 同一 field に複数 source_ref がある場合、該当 ref index だけに bbox が付くことを確認
  - PDF以外の source_ref を skip することを確認

## 変更しなかったもの

- `BBOX_TARGET_FIELDS` は維持
- bbox保存形式は既存の `{ y_min, x_min, y_max, x_max }` を維持
- frontend の `PdfViewer` は変更なし

## 確認結果

2026-05-31 に実データ1件で確認済み。

- `visa-app/backend` で `.venv/bin/python -m pytest -q` を実行し、108件すべて通過。
- PDF source_ref に対して bbox locator が実行された。
- `source_refs` 57件中、bbox付きは24件。
- レビュー画面でPDF由来フィールドをクリックし、PDFタブ切り替えとbboxハイライト表示を確認した。
- 詳細: [QA_REAL_DATA_2026-05-31.md](QA_REAL_DATA_2026-05-31.md)
