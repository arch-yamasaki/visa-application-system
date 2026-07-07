# 02 PDF bbox 改善

Status: 実装済み / 方針更新あり

> **2026-07-08 更新**: 本文中の `BBOX_TARGET_FIELDS` は現在 `PDF_GEMINI_BBOX_FIELDS` に一本化済み（aliasは削除）。
> 対象は固定列挙に加えて `PDF_GEMINI_BBOX_FIELD_PREFIXES`（`applicant.employment_history.` / `applicant.education.`）の
> prefix一致で判定する。候補生成には品質フィルタ（値エコー・短すぎるquoteの除外）と
> 同一(document, page, locator)の重複集約が入り、candidate は `targets: [(field_path, ref_index), ...]` を持つ
> （旧 `ref_index` 単一形式から変更）。ambiguous は候補位置を `anchor.candidates`（最大3件）として保存し、
> ビューアで全候補を表示・移動できる。詳細は `../009_evidence_candidates/README.md` を参照。

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

## 方針更新: BBOX_TARGET_FIELDS と anchor の責務

2026-07 時点の実データ確認で、次の問題が見えた。

- `employer.employment_insurance_office_number` は抽出schemaにはあるが、`BBOX_TARGET_FIELDS` にないため、画像PDFでは bbox 候補にならない。
- `employer.postal_code` は `BBOX_TARGET_FIELDS` にあるが、Gemini が返す `source_ref.page` がずれると、bbox locator は誤ったページだけを探して失敗する。
- スキャン画像PDFでは PDF text layer / PDF.js text fallback が使えないため、bbox が付かないと画面では何も光らない。

短期対応として、抜けている主要fieldを `BBOX_TARGET_FIELDS` に追加するのは有効。ただし、根本設計としては `BBOX_TARGET_FIELDS` を「bboxを付けるfield一覧」として使い続けない。

推奨する責務分離は次。

```text
source_ref
  |
  |-- document_id    抽出時にGeminiが根拠として示した文書
  |-- page           抽出時にGeminiが根拠として示したページ
  |-- text_quote     人間に見せる根拠引用
  `-- confidence     抽出の自信度

anchor
  |
  |-- status         resolved / ambiguous / not_found / skipped_unsupported
  |-- resolver_type  pdf_text_layer / gemini_bbox / ocr_bbox など
  |-- page           viewer が実際に開くページ
  `-- bbox           viewer が実際に光らせる座標
```

`source_ref.page` は「抽出モデルが言ったページ」であり、必ずしも表示に使える正解ページではない。`anchor.page` は resolver が実際に場所を特定できたページとして扱う。

```json
{
  "document_id": "company_documents",
  "page": 22,
  "text_quote": "東京都渋谷区千駄ヶ谷4-25-2 151-8570",
  "confidence": 0.9,
  "anchor": {
    "type": "pdf_bbox",
    "status": "resolved",
    "resolver_type": "gemini_bbox",
    "page": 20,
    "bbox": {
      "y_min": 320,
      "x_min": 180,
      "y_max": 350,
      "x_max": 310
    }
  }
}
```

この形なら、Gemini の `source_ref.page` がずれていても、resolver が別ページで一意に見つけた場合は `anchor.page` を使って正しい場所へジャンプできる。

### bbox candidate の作り方

現在は `BBOX_TARGET_FIELDS` 起点で candidate を作っている。

```text
field_path が BBOX_TARGET_FIELDS にある
  |
  v
source_refs[] を bbox candidate にする
```

本命設計では、`source_ref` 起点に変える。

```text
field_metadata.source_refs[]
  |
  |-- document_id がPDF
  |-- text_quote または locator_text がある
  |-- anchor が未解決
  `-- bbox が未付与
        |
        v
      bbox candidate にする
```

`BBOX_TARGET_FIELDS` は、将来的には次のどちらかに役割を変える。

| 方針 | 内容 | 判断 |
|---|---|---|
| 廃止 | PDF source_ref があるものは原則 candidate 化する | 可読性は高い。候補数とGemini bboxコストに注意 |
| 優先度/高コスト制御へ変更 | source_ref candidate は作るが、Gemini画像bboxに回すfieldだけ制限する | MVPでは現実的 |

MVPでは後者がよい。名前も `BBOX_TARGET_FIELDS` より、`PDF_GEMINI_BBOX_FIELDS` の方が意味が明確。

```text
PDF source_ref
  |
  v
まず deterministic resolver を試す
  |
  |-- PDF text-layer word bbox
  |-- OCR word bbox
  `-- 形式別の軽いresolver
        |
        v
未解決かつ主要fieldなら Gemini bbox fallback
```

### 抽出Geminiに bbox を返させない理由

抽出時に `page` と `bbox` を同時に返させる案は、初期実装では採用しない。

理由は、抽出と場所特定の責務が違うため。

```text
抽出
  何の値かを決める
  例: 郵便番号は 151-8570

場所特定
  原本のどこにあるかを決める
  例: PDF 20ページ目のこの座標
```

1回のGemini応答に値・page・bboxを全部持たせると、値は正しいがpageだけ違う、bboxだけ違う、という失敗を切り分けにくい。したがって、Gemini抽出は `source_ref` まで、resolver が `anchor` を補完する。

### viewer の優先順位

frontend は次の優先順位に寄せる。

```text
表示ページ
  1. source_ref.anchor.page
  2. source_ref.page

ハイライト
  1. source_ref.anchor.bbox
  2. source_ref.bbox
  3. text_quote fallback
```

既存互換のため、当面は top-level `bbox` も維持してよい。ただし、新しい実装では `anchor.bbox` を正とし、top-level `bbox` はPDF viewer互換のミラーとして扱う。

### 実装計画

1. 短期修正として、`employer.employment_insurance_office_number` など明らかに漏れている主要fieldを `BBOX_TARGET_FIELDS` に追加する。実装済み。
2. `anchor` に `page` を持てるよう schema / TypeScript 型 / frontend navigation を揃える。実装済み。
3. `viewerStore.navigateToSource()` は `ref.anchor.page ?? ref.page ?? 1` を使う。実装済み。
4. `bbox_locator.py` の candidate 生成を PDF `source_ref` 起点へ変更する。2026-07-08 に prefix対応・品質フィルタ・重複集約まで実装済み。allowlist の完全削除は `candidates_filtered` メトリクスの実測を見てから判断する。
5. Gemini bbox fallback の対象制御として `PDF_GEMINI_BBOX_FIELDS` を導入するか、候補数上限で制御する。実装済み。
6. `sync_bbox_anchors()` は top-level `bbox` を `anchor.bbox` へ同期する互換処理として残す。実装済み。ただし `ambiguous` は resolved に昇格しない。
7. `anchor.status`, `resolver_type`, `match_count` をQAで確認できるようにログとテストを追加する。実装済み。

### 2026-07 実装メモ

Claude Codeレビュー相当の観点で、次を追加実装した。

- PDF resolved anchor に `page` を保存する。
- frontend は `anchor.page` を `source_ref.page` より優先して開く。
- `source_ref.page` に見つからないPDF text-layer match は、他ページも探索し、一意なら `anchor.page` に保存する。
- `ambiguous` anchor は Gemini bbox fallback と bbox同期で resolved に昇格しない。
- XLSX / DOCX の短いquoteは、完全一致だけ resolved にする。短い substring 一致は resolved にしない。
- PDF Gemini bbox の高コスト対象名を `PDF_GEMINI_BBOX_FIELDS` に寄せる（`BBOX_TARGET_FIELDS` alias はその後削除済み）。
- `employer.employment_insurance_office_number` を PDF Gemini bbox 対象に追加した。
- PDF viewer は `anchor.status === "resolved"` の時だけ `anchor.bbox` / legacy `bbox` を確定ハイライトとして使う。

### 2026-07 実装メモ(コードレビュー後の修正)

マルチエージェントレビューで見つかった問題への修正。

- 冪等性: `existing_bbox` 経路は、resolved 済み anchor を上書きしない。クロスページ解決後に `resolve_anchors()` を再実行しても、`anchor.page` が `source_ref.page` に巻き戻らない。
- 探索順: locator target は「強い順」(フル quote → 単語境界80文字プレフィックス → 数値パターン)で、各 target が「指定ページ → 他ページ」を先に使い切る。弱い数値パターンが指定ページで誤ヒットして、フル quote のクロスページ一意一致を潰さない。
- 長い quote: 旧実装の `quote[:80]` は単語の途中で切れると word-join 完全一致が成立しなかった。フル quote を第一 target にし、80文字トランケートは単語境界で切る第二 target に変更。
- PDF viewer: `anchor.status` が `ambiguous` の時だけ legacy top-level `bbox` を抑制する。`not_found` や status なしの legacy データでは top-level `bbox` を表示する(Gemini bbox 由来の別根拠のため)。
- 効率: `resolve_anchors()` は文書ごとに PDF を1回だけパースし、ページの word 抽出・正規化を `_PdfTextIndex` にキャッシュする。
- `_page_number` を `anchor_resolver` に一本化し、`bbox_locator` は import して使う。

まだ残っている課題:

- allowlist（`PDF_GEMINI_BBOX_FIELDS`）の完全削除。prefix対応・品質フィルタ・重複集約は実装済みで、削除判断は `candidates_filtered` メトリクスの実測待ち。
- OCR word bbox resolver を追加すること。
- ambiguous の自動解消（周辺文脈での絞り込み）。現状は候補位置を `anchor.candidates` として保存し、人が候補間を移動して判断する（`../009_evidence_candidates/README.md`）。

### 受け入れ条件の更新

- PDF source_ref がある主要fieldは、field allowlist漏れで bbox 候補から落ちない。
- `source_ref.page` がずれていても、resolver が別ページで一意に特定できた場合は `anchor.page` で表示できる。
- 抽出結果の `source_ref` と、表示用の `anchor` が別責務として読める。
- 画像PDFでは、PDF text fallback だけに依存せず Gemini bbox / OCR bbox のどちらかに回せる。
- bbox取得失敗は抽出失敗にしない。`anchor.status = not_found` などで状態を残す。

## 確認結果

2026-05-31 に実データ1件で確認済み。

- `visa-app/backend` で `.venv/bin/python -m pytest -q` を実行し、108件すべて通過。
- PDF source_ref に対して bbox locator が実行された。
- `source_refs` 57件中、bbox付きは24件。
- レビュー画面でPDF由来フィールドをクリックし、PDFタブ切り替えとbboxハイライト表示を確認した。
