# 009: 証跡候補の複数表示（位置候補ナビ + 値候補 alternatives）

Status: Part A 実装済み / Part B 実装済み（2026-07-08）

## 背景・目的

レビューの核心は「どの書類のどの記載を根拠に、この値になったか」を人が確認することにある。
現実の書類束では次の2種類の「複数候補」が発生する。

1. **位置候補**: 値は1つだが、同じ文字列が書類内に複数箇所あり、どこが本当の証跡か機械的に確定できない
   （例: 履歴書内の「October 2024」が前職の退職時期と現職の入社時期の両方に出現）
2. **値候補**: 書類間・箇所間で **値そのものが食い違う**
   （例: 履歴書の給与とオファーレターの給与が異なる、COEヒアリングシートと履歴書で卒業年月が違う）

特に 2 が重要。複数の情報源が違う値を示しているとき、レビュアが「どれが正しそうか」を
見比べて判断・確定できることが、このアプリの価値の中心になる。

- Part A（位置候補）: ambiguous な anchor の候補位置を全部保存し、ビューアで候補間を移動できるようにする → **実装済み**
- Part B（値候補）: 抽出時に食い違う値を alternatives として保持し、UIで見比べ・クリック採用できるようにする → **本ドキュメントの仕様で実装する**

ユーザー決定事項（2026-07-08）:

- 位置候補のナビは **PDFビューア側** に置く（証跡を見ながら移動する動線）
- 値候補は **FieldValueスキーマ拡張**（抽出1パス、field と候補が構造的に紐付く方式）で実装する
- 値候補は **クリックで採用**（case_data の値が置き換わる）できるようにする
- リリースは A 先行 → B。B は別の実装者（AI）が本ドキュメントを見て実装する

---

## Part A: 位置候補ナビ（実装済み）

### データ形状

`anchor_resolver.py` が PDF text layer 検索で複数一致を検出したとき、
`source_ref.anchor` に候補位置を保存する（最大 `MAX_AMBIGUOUS_CANDIDATES = 3` 件）。

```json
{
  "type": "pdf_bbox",
  "status": "ambiguous",
  "resolver_type": "pdf_text_layer",
  "match_count": 3,
  "candidates": [
    { "page": 1, "bbox": { "y_min": 492, "x_min": 449, "y_max": 515, "x_max": 501 } },
    { "page": 2, "bbox": { "...": 0 } }
  ]
}
```

- `match_count` は実一致数（candidates は上限で切り詰められる場合がある）
- top-level `ref.bbox` は「確定した単一位置」の意味なので ambiguous では付けない

### 実装箇所

| ファイル | 内容 |
|---|---|
| `backend/extractors/anchor_resolver.py` | `_set_ambiguous_pdf_anchor()` が candidates を保存。`_normalize_text` は括弧 `()（）` も除去（括弧付き日付とquoteの一致のため） |
| `frontend/src/types/caseData.ts` | `SourceAnchor.candidates?: {page?, bbox}[]` |
| `frontend/src/store/viewerStore.ts` | `activeCandidateIndex` / `goToCandidate(index)`。候補移動はハイライトを保ったままページだけ追従（`setPage` はハイライトを消すので使わない） |
| `frontend/src/components/viewer/PdfViewer.tsx` | 候補を破線ハイライトで全件描画、アクティブ候補は強調スタイル。候補が2件以上のときフローティングナビ「候補 1/3 ← →」をビューア上部に表示 |
| `frontend/src/components/review/FieldRow.tsx` | primary ref が ambiguous のとき「候補N」バッジ表示 |

### 既知の制約

- PDF のみ。xlsx / docx の ambiguous（`_resolve_from_text_index`）は candidates 未対応。
  対応する場合は structural anchor の候補（cell / paragraph_index）を同様に保存し、`HtmlViewer` に複数ハイライトを実装する
- 保存済みケースへの反映は `POST /cases/{case_id}/reanchor`（Gemini再抽出なしでanchor/bboxのみ再計算し、`anchor_coverage` を保存する）

---

## Part B: 値候補 alternatives（実装仕様）

### 現状アーキテクチャ（実装前に必ず把握すること）

抽出データの流れ:

```
prompt_template.py ─┐
schema.py ──────────┤→ Gemini structured output
                    │   各末端フィールド = {"value": ..., "source_ref": {document_id, page, text_quote, confidence}}
                    ↓
gemini.py
  _normalize_fieldvalue()   {value, source_ref} → {value, source_refs: [ref]} に変換
  _extract_field_metadata() case_data ツリーを走査し field_metadata["a.b.0.c"] = {source_refs, confidence} を生成
  （※ Gemini が source_refs を直接返す旧形式は _uses_raw_source_refs() で明示的に拒否している）
                    ↓
gemini_pipeline.attach_bboxes()
  anchor_resolver.resolve_anchors()  … source_refs[].anchor を解決（text layer / xlsx / docx）
  bbox_locator.locate_bboxes()       … 未解決 ref に Gemini 画像 bbox を付与
  anchor_resolver.sync_bbox_anchors()
                    ↓
Firestore cases/{case_id}.field_metadata / case_data
                    ↓
frontend FieldRow → pickPrimarySourceRef() → viewerStore.navigateToSource() → PdfViewer/HtmlViewer
```

重要な事実:

- FieldValue スキーマは `schema.py` の `FIELD_VALUE_SCHEMA` と `_fv()` に集約されており、
  全スコープ（S1〜S6）の `_object_of_fields()` がこれを使う。**1箇所直せば全フィールドに効く**
- `field_metadata` の値は `{source_refs: [...], confidence}` の dict。ここに任意キーを足しても
  Firestore・API・既存UIはそのまま通る（後方互換）
- FieldRow には編集フロー（`onUpdate(fieldPath, value)` → 保存ボタンで PATCH `/cases/{id}`）が既にある。
  「採用」はこのフローを再利用する

### B-1. スキーマ変更（schema.py）

`FIELD_VALUE_SCHEMA` に `alternatives` を追加する:

```python
FIELD_VALUE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "value": STRING_VALUE_SCHEMA,
        "source_ref": SOURCE_REF_SCHEMA,
        "alternatives": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "value": STRING_VALUE_SCHEMA,   # 注意: _fv() で value 型を差し替える際、
                    "source_ref": SOURCE_REF_SCHEMA, # alternatives.items.value も同じ型に差し替えること
                },
                "required": ["value", "source_ref"],
            },
        },
    },
    "required": ["value", "source_ref"],  # alternatives は required にしない
}
```

- `_fv(value_schema)` は `properties.value` に加えて
  `properties.alternatives.items.properties.value` も差し替えるよう修正する
- `alternatives` を required にすると Gemini が全フィールドで空配列を返しトークンを浪費するため
  optional のままにする

### B-2. プロンプト変更（prompt_template.py）

FieldValue の形式を説明している全箇所（スコープ版・非スコープ版の両方がある。
`{"value": "...", "source_ref": ...}` で grep すること）に以下の指示を追加する:

```
- 同一フィールドについて、複数の書類・箇所が「互いに異なる値」を示している場合のみ、
  最有力の値を value に、それ以外の候補を alternatives に入れること
  （各候補も {"value": ..., "source_ref": ...} 形式で、証跡必須）
- 値が一致している場合や候補が1つしかない場合、alternatives は省略すること
- alternatives は最大2件。同じ値の重複は入れないこと
```

OK/NG例も1組追加する（例: 履歴書とオファーレターで給与が異なるケース）。

### B-3. 正規化（gemini.py）

1. `_uses_raw_source_refs()` の拒否ロジックが `alternatives` を誤検知しないことを確認する
   （alternatives の items は `source_ref`（単数）なので現状ロジックでは問題ないはずだが、テストを書く）
2. `_normalize_fieldvalue()`: `{value, source_ref, alternatives}` →

```python
{
    "value": ...,
    "source_refs": [primary_ref],
    "alternatives": [
        {"value": alt_value, "source_refs": [alt_ref]},
        ...
    ],
}
```

3. `_extract_field_metadata()`: field_metadata 項目に alternatives を含める:

```python
field_metadata[path] = {
    "source_refs": [...],
    "confidence": ...,
    "alternatives": [{"value": ..., "source_refs": [...]}, ...],  # ある場合のみ
}
```

4. **品質ガード**（正規化時に適用し、弾いた件数を logger.info でメトリクス出力）:
   - `value` が primary と正規化後同値（trim / NFKC / lower）の候補は捨てる
   - `value` が空、または `source_ref.text_quote` が空の候補は捨てる
   - 3件以上返ってきたら先頭2件に切り詰める
   - display用 case_data（`_strip_field_metadata` 相当）には alternatives を残さない（valueのみ）

### B-4. anchor / bbox 対応

alternatives 内の ref にも位置解決を効かせる。

- `anchor_resolver.resolve_anchors()` と `sync_bbox_anchors()`: meta の走査ループで
  `meta["source_refs"]` に加えて `meta.get("alternatives", [])` の各 `alt["source_refs"]` も同じ処理にかける
  （ループを関数化して共通化するのが良い。`_iter_all_refs(meta)` のようなジェネレータを追加）
- `bbox_locator.locate_bboxes()`: 候補収集ループも同様に alternatives の refs を走査する。
  candidate の適用先が `(field_path, ref_index)` の2要素タプルなので、
  alternatives 対応では `(field_path, alt_index or None, ref_index)` の形に拡張が必要
- Part A の ambiguous candidates は alternatives の ref にもそのまま効く（同じ構造のため）

### B-5. フロントエンド

1. `types/caseData.ts`:

```ts
export interface FieldAlternative {
  value: string
  source_refs?: SourceRef[]
}
// FieldMeta に alternatives?: FieldAlternative[] を追加
```

2. `FieldRow.tsx`:
   - `meta.alternatives` が1件以上あるとき「**別候補N**」バッジを表示（Part Aの「候補N」= 位置、
     こちらは値の競合なので **色を変える**。位置=amber、値=red系 を推奨。値競合の方が重要度が高い）
   - 行クリックで従来どおり primary の証跡へジャンプ
   - バッジ（または行の展開トグル）クリックで **候補リストを行下に展開**:
     - 各候補行: `値 / 書類名 / text_quote（先頭40字）/ p.N`
     - 候補行クリック → `navigateToSource(alt.source_refs[0])` で証跡ジャンプ
     - 「採用」ボタン → `onUpdate(fieldPath, alt.value)`（既存の編集保存フローに乗せる。
       採用後も meta.alternatives は残す = 判断の履歴が消えない）
     - primary の値にも「現在の値」として同列に表示し、証跡ジャンプできるようにする
3. ドキュメント名の解決は `viewerStore.documents`（`document_manifest.documents`）から
   `document_id` で引く（`DocumentViewer` のタブと同じやり方）

### B-6. テスト計画

backend（`backend/tests/`、実行は `.venv/bin/python -m pytest -q`）:

- `test_gemini.py`: alternatives 付き FieldValue の正規化
  （primary と同値の候補が落ちる / 空quoteが落ちる / 2件に切り詰め / alternatives 無しは従来通り）
- `test_schema.py`: `_fv(BOOLEAN_VALUE_SCHEMA)` で alternatives.items.value も BOOLEAN になる
- `test_anchor_resolver.py`: alternatives 内 ref の anchor が解決される
- `test_bbox_locator.py`: alternatives 内 ref が bbox 候補になる

eval（品質検証。**スキーマ+プロンプト変更なので必須**）:

- `qa/test-files/eval-cases/` の4ケース（amit_tamang, shekhar_dahal, bhawana_khanal, manoj_mukhiya）を
  ローカルbackendから抽出し、以下を目視確認:
  - alternatives が「本当に値が食い違う箇所」にだけ付いているか（過剰検出していないか）
  - 従来フィールドの抽出品質が落ちていないか（amit_tamang は
    `visa-eval/test_cases_from_raw/gijinkoku_a_company_round1/amit_tamang/expected/case_data.golden.json` と比較）
  - レスポンストークン量の増分が許容範囲か（ログの usage を確認）

### B-7. QA手順

1. ローカル起動（`visa-app/CLAUDE.md` 参照。認証必須になったのでログインが要る）
2. eval-cases のいずれかで新規ケース作成 → 抽出
3. 値が食い違うフィールドに「別候補」バッジが出る → 展開 → 候補クリックでPDFの該当箇所が光る
   → 「採用」で値が置き換わり保存できる、を確認
4. スクリーンショットを `qa/screenshots/<日付>/` に保存し、`qa/` にQA記録mdを残す

### B-8. リスクと軽減策

| リスク | 軽減策 |
|---|---|
| Gemini が alternatives を過剰に埋める（同値・言い換えを競合扱い） | プロンプトで「互いに異なる値のみ」「省略が基本」を明示 + B-3の同値ガード + eval で precision 確認 |
| レスポンス肥大・抽出時間増 | optional スキーマ + 最大2件 + eval でトークン実測 |
| 旧形式検知 `_uses_raw_source_refs` の誤爆 | alternatives は `source_ref`（単数）なので構造上衝突しないが、ユニットテストで固定 |
| 保存済みケースとの互換 | field_metadata への追加キーのみなので後方互換。alternatives が無いケースはバッジが出ないだけ |
| 「採用」で証跡と値がずれる（valueだけ変わり source_refs は primary のまま） | 採用時に field_metadata の primary を差し替えるのは v1 ではやらない（編集=人の判断として扱う）。将来 PATCH に metadata 更新を足す場合は 007 の source_refs スキーマ移行ドキュメントを参照 |

### B-9. 実装結果（2026-07-08）

実装済み:

- `backend/extractors/schema.py`: `FIELD_VALUE_SCHEMA` に optional `alternatives` を追加し、`_fv()` で BOOLEAN / INTEGER などの value 型を alternatives 側にも反映
- `backend/extractors/prompt_template.py`: legacy prompt / scoped prompt の両方に、値が食い違う場合のみ `alternatives` を最大2件返す指示と給与のOK/NG例を追加
- `backend/extractors/gemini.py`: alternatives の正規化、同値・空値・空quote除外、最大2件への切り詰め、`field_metadata[path].alternatives` への保持を実装。表示用 `case_data` は value-only のまま
- `backend/extractors/anchor_resolver.py`: primary refs と alternatives refs を共通走査し、PDF / DOCX / XLSX anchor と bbox同期を alternatives にも適用
- `backend/extractors/bbox_locator.py`: alternatives refs を bbox 候補に含め、`(field_path, alt_index, ref_index)` で正しい ref に bbox を戻す
- `frontend/src/types/caseData.ts`: `FieldAlternative` と `FieldMeta.alternatives` を追加
- `frontend/src/pages/ReviewPage.tsx`: list形式 `field_metadata` 正規化時にも alternatives を保持
- `frontend/src/components/review/FieldRow.tsx`: 赤系の `別候補N` バッジ、展開リスト、候補証跡ジャンプ、既存編集フローを使う `採用` ボタンを追加
- `frontend/src/api/mockData.ts` / `frontend/e2e/review-flow.spec.ts`: デモケースに値候補を追加し、展開・採用のE2Eを追加

確認済み:

- `cd visa-app/backend && .venv/bin/python -m pytest -q` → 171 passed
- `cd visa-app/frontend && npm run build` → success
- `cd visa-app/frontend && npx playwright test` → 18 passed

未実施:

- B-6 の実資料 eval 4ケースによる alternatives precision / token 増分 / Amit golden 比較
- 認証付きローカル実画面での新規ケース抽出、スクリーンショット保存、QA記録作成

### B-10. 実装順序チェックリスト

1. [x] schema.py: FIELD_VALUE_SCHEMA / _fv() に alternatives 追加 + テスト
2. [x] prompt_template.py: 指示文追加（スコープ版・非スコープ版の両方）
3. [x] gemini.py: 正規化 + 品質ガード + テスト
4. [x] anchor_resolver.py / bbox_locator.py: alternatives refs の走査 + テスト
5. [x] frontend: 型 → FieldRow 展開UI・採用ボタン → ビルド
6. [ ] eval-cases で抽出品質・過剰検出・トークン増を確認
7. [ ] 実画面QA → qa/ に記録 → commit → デプロイ

---

## 将来課題（本設計のスコープ外）

- xlsx / docx の位置候補（HtmlViewer の複数ハイライト）
- 「どれが正しいか」をAIに質問する / AIが推奨理由を説明するフロー（値候補UIの上に載せる）
- 申請人への不足確認・再依頼テンプレートへの競合情報の組み込み
