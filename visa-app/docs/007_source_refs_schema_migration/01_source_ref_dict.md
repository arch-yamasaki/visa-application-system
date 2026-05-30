# 01 source_ref dict 化

Status: 実装済み

## 目的

Gemini raw response の証跡表現を、文字列から意味のある dict に変える。

現状:

```json
{
  "value": "AMIT TAMANG",
  "source": "doc_abc123|1|AMIT TAMANG|0.95"
}
```

変更後:

```json
{
  "value": "AMIT TAMANG",
  "source_ref": {
    "document_id": "doc_abc123",
    "page": 1,
    "text_quote": "AMIT TAMANG",
    "confidence": 0.95
  }
}
```

値が見つからない場合:

```json
{
  "value": "",
  "source_ref": {
    "document_id": "",
    "page": 0,
    "text_quote": "",
    "confidence": 0
  }
}
```

## なぜ array にしないか

現行 UI は primary evidence として `source_refs[0]` だけを使っている。Gemini に複数証跡を直接返させても、今のレビュー画面では実益が薄い。

また、Gemini response schema は複雑化すると `too many states` 系の制約に当たりやすい。配列の `source_refs[]` より、単一 `source_ref` dict の方が schema が軽い。

## 保存形式

Firestore の保存契約は当面変えない。

| データ | 役割 |
|---|---|
| `case_data` | value-only の申請データ |
| `field_metadata` | canonical path ごとの証跡・bbox・編集情報 |
| `review` | 不足・矛盾・注意点 |

backend 内部では、Gemini の `source_ref` を既存の `field_metadata.source_refs[]` に変換して保存する。

## 対象ファイル

| ファイル | 変更方針 |
|---|---|
| `backend/extractors/schema.py` | `FIELD_VALUE_SCHEMA` を `{ value, source_ref }` にする |
| `backend/extractors/prompt_template.py` | `source` 文字列指示を `source_ref` dict 指示にする |
| `backend/extractors/gemini.py` | `source_ref` dict を `source_refs[]` に正規化する |
| `frontend/src/types/caseData.ts` | すぐには変更しない。保存形式維持のため `source_refs[]` のまま |

## 作業計画

1. `schema.py` に `SOURCE_REF_SCHEMA` を追加する。
2. `FIELD_VALUE_SCHEMA` を `{ value, source_ref }` に変更する。
3. `prompt_template.py` の証跡要件を `source_ref` dict 前提に書き換える。
4. `gemini.py` の `_unflatten_field_values()` に `source_ref` dict 正規化を追加する。
5. 旧 `source` 文字列の互換処理は初回は残す。
6. 実データで Gemini schema error が出ないか確認する。
7. 安定後に旧 `source` 文字列の説明と互換処理を削除する。

## 空 source_ref の扱い

Gemini response schema の安定性を優先し、`source_ref: null` は採用しない。値が見つからない場合は次の空 object を返す。

```json
{
  "value": "",
  "source_ref": {
    "document_id": "",
    "page": 0,
    "text_quote": "",
    "confidence": 0
  }
}
```

backend 保存時はこの空 source_ref を `field_metadata.source_refs[]` に入れない。UIに空の証跡が出ると、クリックしても何も起きない行が増えるため。

## レビュー観点

| 観点 | 確認すること |
|---|---|
| PdM | `case_data` が value-only のままで、レビュー画面の使い勝手が変わらない |
| UI/UX | 既存の `source_refs[0]` ジャンプが壊れない |
| Lead Engineer | Gemini raw response と保存形式の境界が明確 |
| Engineer | 旧 `source` 互換処理を初回は残し、削除タイミングを分ける |
| QA | 実データ1件で schema error、bbox、レビュー画面、Chrome拡張APIを確認する |

## 受け入れ条件

- Gemini raw response が `{ value, source_ref }` 形式で返る。
- Firestore の `field_metadata.source_refs[]` は既存UI互換として維持される。
- 既存の PDF bbox 付与が壊れない。
- Chrome拡張の `/application-data` には影響しない。

## 注意点

`source_ref` は primary evidence 1件を表す。複数証跡を持ちたい場合は、将来の `field_metadata` 側で扱う。

## 実装内容

- `backend/extractors/schema.py`
  - `SOURCE_REF_SCHEMA` を追加
  - `FIELD_VALUE_SCHEMA` を `{ value, source_ref }` に変更
  - `source_ref` は nullable にせず、値がない場合は空 object を返す契約にした
- `backend/extractors/prompt_template.py`
  - 通常prompt / scoped prompt の証跡指示を `source_ref` dict に変更
- `backend/extractors/gemini.py`
  - `{ value, source_ref }` を `{ value, source_refs: [...] }` に正規化
  - 旧 `{ value, source }` 文字列互換は維持
  - `confidence` の文字列正規化を追加
- `backend/tests/test_gemini.py`
  - `source_ref` dict の正規化テストを追加
  - 旧 `source` 文字列互換テストを維持

## 残した互換処理

- 旧 `source = "document_id|page|text_quote|confidence"` はまだ読める
- 旧 `source_refs[]` raw response もまだ読める
- Firestore / frontend は引き続き `field_metadata.source_refs[]` を読む

## 確認結果

2026-05-31 に実データ1件で確認済み。

- `visa-app/backend` で `.venv/bin/python -m pytest -q` を実行し、108件すべて通過。
- 実Gemini APIで `{ value, source_ref }` response schema が通った。
- Firestore保存後、`case_data` は value-only のまま。
- 証跡は `field_metadata.*.source_refs[]` に保存された。
- 詳細: [QA_REAL_DATA_2026-05-31.md](QA_REAL_DATA_2026-05-31.md)
