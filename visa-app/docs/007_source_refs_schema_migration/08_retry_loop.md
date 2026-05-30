# 08 bbox retry / scope retry loop

## 目的

抽出と証跡構造が安定した後に、失敗した箇所だけを再実行できるようにする。

初期MVPの `workflow_state` は増やさない。ユーザーに見せる案件状態は `draft / extracting / extracted / failed` のままにし、retry の詳細状態は extraction run の履歴として分離する。

## 調査対象

| ファイル | 確認した役割 |
|---|---|
| `backend/main.py` | `/cases/{case_id}/extract-stream`、Firestore保存、`ExtractRequest` |
| `backend/extractors/gemini_pipeline.py` | scoped extraction と bbox 付与の接続 |
| `backend/extractors/gemini.py` | scope並列抽出、review実行、`field_metadata` 生成 |
| `backend/extractors/bbox_locator.py` | PDF source_ref への bbox 付与 |
| `frontend/src/pages/ReviewPage.tsx` | review画面の保存、`human_edited` 付与 |
| `frontend/src/api/client.ts` | `/extract-stream` SSE client |
| `frontend/src/types/caseData.ts` | `SourceRef`, `FieldMeta`, `Review` 型 |

## 現状

### `/cases/{case_id}/extract-stream`

現在の流れは次の通り。

1. `workflow_state=extracting` にする。
2. `_extract_with_gemini()` を実行する。
3. `result.display_case_data` を既存 `case_data` に deep merge する。
4. `review` と `field_metadata` は最新抽出結果で置き換える。
5. `extraction` に最新run情報を保存する。
6. `workflow_state=extracted` にする。
7. 例外時は `workflow_state=failed` にする。

重要なのは、`case_data` は merge だが、`field_metadata` は置換であること。現状のまま retry を入れると、人が編集した field の `human_edited=true` が消える可能性がある。

### `gemini_pipeline.py`

`extract_documents()` は scoped extraction のとき、現在は `identity / employer / education / review` を使う。

ただし、各scopeに渡す `contents` と `documents` は現状すべて同じで、document routing はまだ効いていない。

抽出後に `attach_bboxes()` が呼ばれ、PDF由来の `source_refs` に bbox が付く。bbox が失敗しても抽出結果は返る。

### `gemini.py` scoped extraction

`extract_all_scopes()` は `identity / employer / education` を並列実行し、その後 `review` を実行する。

一部scopeが失敗しても、全scope失敗でなければ部分結果を返す。失敗scopeは `review.validation_errors` と `review.findings` に文字列で追加される。

retry loop には `scope`, `reason`, `target_paths` が必要だが、現状の review は retry 制御用の構造ではない。

### `field_metadata`

`field_metadata` は canonical path keyed の dict。

```json
{
  "applicant.name_roman": {
    "source_refs": [
      {
        "document_id": "doc_abc123",
        "page": 1,
        "text_quote": "AMIT TAMANG",
        "confidence": 0.95,
        "bbox": { "y_min": 100, "x_min": 120, "y_max": 140, "x_max": 300 }
      }
    ],
    "human_edited": false
  }
}
```

レビュー画面で人が値を編集すると、frontend が該当 path の `human_edited=true` を付けて保存する。

### frontend review save

`frontend/src/pages/ReviewPage.tsx` は `case_data`, `settings`, `field_metadata` を PATCH する。

値編集時に `human_edited=true` を付ける実装はすでにある。retry loop はこの情報を保護条件として使う。

## 設計方針

### `workflow_state` は増やさない

`workflow_state` は案件全体の業務状態として残す。

retry loop 用に `retrying`, `bbox_retrying`, `scope_retrying` のような状態は増やさない。ユーザーに見せる状態と内部処理状態が混ざるため。

| 状態 | 意味 |
|---|---|
| `draft` | 未抽出 |
| `extracting` | 全体抽出中 |
| `extracted` | 抽出結果あり。レビュー・保存・Chrome拡張投入が可能 |
| `failed` | 全体抽出に失敗 |

retry の進捗は SSE と extraction run 履歴で扱う。

### retry run は案件状態から分離する

推奨は `cases/{case_id}/extraction_runs/{run_id}` の subcollection。

top-level `extraction` は最新runの要約だけにする。

```json
{
  "extraction": {
    "backend": "gemini",
    "latest_run_id": "run_abc123",
    "latest_mode": "scope_retry",
    "completed_at": "2026-05-30T00:00:00Z"
  }
}
```

run履歴は次の形にする。

```json
{
  "run_id": "run_abc123",
  "mode": "scope_retry",
  "status": "completed",
  "backend": "gemini",
  "target_scopes": ["employment"],
  "target_paths": [
    "employment.monthly_salary",
    "employment.joining_date"
  ],
  "started_at": "2026-05-30T00:00:00Z",
  "completed_at": "2026-05-30T00:01:20Z",
  "error_type": null
}
```

初期実装では、run履歴は最新数件だけ見られればよい。UIに最初から表示する必要はない。

### retry mode

初期は3種類に絞る。

| mode | 役割 | 入力 | 保存対象 |
|---|---|---|---|
| `bbox_retry` | 既存 `source_refs` から bbox だけ再取得 | `target_paths` optional | `field_metadata.source_refs[].bbox` |
| `scope_retry` | 特定scopeだけ再抽出 | `target_scopes` required | 対象scopeの `case_data` と `field_metadata` |
| `review_retry` | 抽出済み `case_data` を再レビュー | `target_paths` optional | `review` |

`full` は既存 `/extract-stream` のまま扱う。retry loop の初期対象に single field retry は入れない。

## API 設計

### 最小案

既存 `/cases/{case_id}/extract-stream` を拡張する。

```json
{
  "backend": "gemini",
  "pattern": "auto",
  "scoped": true,
  "mode": "scope_retry",
  "target_scopes": ["employment"],
  "target_paths": []
}
```

`ExtractRequest` に追加する項目。

```python
class ExtractRequest(BaseModel):
    backend: str = "gemini"
    pattern: str = "auto"
    scoped: bool = True
    mode: str = "full"
    target_scopes: list[str] = []
    target_paths: list[str] = []
```

mode は最初は文字列で十分。過剰な抽象化はしない。

### 専用API案

後で必要になったら専用APIを切る。

| API | 用途 |
|---|---|
| `POST /cases/{case_id}/extract-stream` | full extraction |
| `POST /cases/{case_id}/retry-stream` | bbox / scope / review retry |

初期は既存API拡張の方が影響範囲が小さい。

## SSE 設計

既存の `progress / complete / error` は維持する。

retry用に phase を増やす。

| event | phase | 意味 |
|---|---|---|
| `progress` | `run_started` | retry run 開始 |
| `progress` | `planning` | 対象scope/path確定 |
| `progress` | `bbox_retrying` | bbox再取得中 |
| `progress` | `scope_retrying` | scope再抽出中 |
| `progress` | `review_retrying` | review再実行中 |
| `progress` | `saving` | Firestore保存中 |
| `complete` | - | retry完了 |
| `error` | - | retry失敗 |

frontend は当面、既存の進捗表示に message を出すだけでよい。retry専用UIは後回し。

## 保存・merge 設計

### human edit 保護

`human_edited=true` の path は自動retryで上書きしない。

対象は `case_data` と `field_metadata` の両方。

```text
if field_metadata[path].human_edited == true:
    keep existing case_data[path]
    keep existing field_metadata[path]
```

これは retry loop の最重要ルール。

### `bbox_retry`

`bbox_retry` は `case_data` と `review` を触らない。

更新対象は `field_metadata.source_refs[].bbox` のみ。

流れ:

1. Firestoreから既存 `field_metadata` を読む。
2. `target_paths` があれば対象pathだけに絞る。
3. PDF bytes を準備する。
4. `locate_bboxes()` を実行する。
5. bbox が付いた `field_metadata` だけ保存する。

このとき `human_edited=true` は保持する。

### `scope_retry`

`scope_retry` は対象scopeだけGeminiを呼ぶ。

保存時は対象scopeに属する path だけ merge する。対象外pathは触らない。

`human_edited=true` の path は対象scope内でも上書きしない。

scopeとpathの対応は、schema定義または review field catalog から決める。初期は backend 側に明示 map を置く方が読みやすい。

例:

```python
SCOPE_PATH_PREFIXES = {
    "identity": ["applicant.", "entry_plan."],
    "employer": ["employer.", "employment."],
    "education": ["applicant.education.", "applicant.qualifications."],
}
```

scope分割を今後増やす場合、この map も一緒に更新する。

### `review_retry`

`review_retry` は `case_data` と `field_metadata` を触らない。

抽出済み `case_data` と `field_metadata` をもとに review scope だけ再実行し、`review` を置き換える。

ただし、将来 `review` に人間の確認結果を持たせる場合は、review 全置換ではなく merge に変える。

## backend 作業計画

### 1. request mode を追加

対象:

- `backend/main.py`

作業:

- `ExtractRequest` に `mode`, `target_scopes`, `target_paths` を追加する。
- `mode=full` の既存挙動を変えない。
- retry mode の分岐だけ追加する。

### 2. run履歴保存を追加

対象:

- `backend/main.py`

作業:

- run開始時に `extraction_runs/{run_id}` を作る。
- complete/error/interrupted で status を更新する。
- top-level `extraction.latest_run_id` を更新する。

初期は top-level `extraction` だけでも動くが、loopを入れるなら履歴を分けた方が読みやすい。

### 3. bbox retry handler を追加

対象:

- `backend/main.py`
- `backend/extractors/gemini_pipeline.py`
- `backend/extractors/bbox_locator.py`

作業:

- 既存 `attach_bboxes()` を再利用できる形に整理する。
- `ExtractionResult` がなくても `field_metadata` に対して bbox を付けられる関数を用意する。
- `bbox_retry` では `case_data` と `review` を保存しない。

削除候補:

- bbox対象の固定 allowlist が肥大化する場合は、後で review catalog 起点へ移す。

### 4. scope retry handler を追加

対象:

- `backend/main.py`
- `backend/extractors/gemini_pipeline.py`
- `backend/extractors/gemini.py`

作業:

- `extract_all_scopes()` に `target_scopes` を渡せるようにする。
- reviewを必ず実行するかどうかを mode で分ける。
- 対象scopeの `display_case_data` と `field_metadata` だけを既存データへ merge する。

初期では document routing は入れない。全書類を対象scopeに渡してよい。

### 5. metadata merge を作る

対象:

- `backend/main.py`

作業:

- `case_data` merge と別に `field_metadata` merge helper を作る。
- `human_edited=true` の path は既存を残す。
- 対象外pathは既存を残す。
- retryで得た新規pathは追加する。

### 6. review retry handler を追加

対象:

- `backend/extractors/gemini.py`
- `backend/main.py`

作業:

- review scopeだけ実行する関数を切り出す。
- 保存対象は `review` のみにする。
- 既存 `case_data` を extra context に渡す。

## frontend 作業計画

### 1. 既存保存動線は維持

対象:

- `frontend/src/pages/ReviewPage.tsx`

既存の `human_edited=true` 付与は残す。retry loop 実装時も、このフラグを backend の保護条件として扱う。

### 2. 初期UIは追加しない

retry loop は最後に入れるため、最初から複雑なボタンは作らない。

必要になったら、次の最小UIだけ追加する。

| UI | 意味 |
|---|---|
| `証跡を再取得` | 選択中fieldの bbox retry |
| `このscopeを再抽出` | 現在sectionに対応する scope retry |
| `レビューを再実行` | review retry |

### 3. SSE client

対象:

- `frontend/src/api/client.ts`

作業:

- `startExtractionStream()` に `mode`, `target_scopes`, `target_paths` を渡せるようにする。
- 既存 `onProgress` の型は大きく変えず、`phase/message` を表示する。

## 削除・整理候補

### retry導入前に消さない

- `workflow_state=extracted` の互換
- `field_metadata.source_refs[]`
- `human_edited`
- `attach_bboxes()`
- `locate_bboxes()`

### retry導入後に整理する

- `review.validation_errors` に scope failure を文字列で入れる処理
  - retry 判定に使いにくいため、将来 `code / scope / severity / message` の object に寄せる。
- `bbox_locator.py` の `BBOX_TARGET_FIELDS`
  - 固定配列が大きくなったら review catalog または source_ref anchor_type 起点へ移す。
- `main.py` 内の full extraction と retry の保存処理重複
  - helper に分ける。ただし最初から抽象化しすぎない。

## リスク

### human edit を上書きするリスク

最も危険。

対策:

- `human_edited=true` の path は `case_data` も `field_metadata` も既存を残す。
- retry結果の保存前に対象pathの diff を作る。

### scope retry で関連fieldの整合が崩れるリスク

例: `employment.monthly_salary` だけ直って、`employment.activity_details` や `employment.contract_type` と整合しない。

対策:

- single field retry は初期で入れない。
- `scope` または `cluster` 単位で再抽出する。

### bbox retry が抽出全体を失敗に見せるリスク

bboxは証跡補助であり、値抽出の成功条件ではない。

対策:

- `bbox_retry` 失敗時も `workflow_state` は `extracted` のままにする。
- run履歴だけ `failed` にする。

### run履歴が肥大化するリスク

対策:

- 初期は最新run要約だけでもよい。
- subcollectionを使う場合も、UI表示は最新数件に限定する。

## 受け入れ条件

loop実装時の最小受け入れ条件は次の通り。

- full extraction の既存挙動が変わらない。
- `bbox_retry` が `case_data` と `review` を変更しない。
- `scope_retry` が対象scope外の `case_data` と `field_metadata` を変更しない。
- `human_edited=true` の値が retry で上書きされない。
- retry失敗で `workflow_state` が `failed` に落ちない。ただし full extraction 失敗は従来通り `failed`。
- SSE が retry の開始、処理中、保存、完了、失敗を返す。

## 実装順

loopは最後に入れる前提なので、順番は次の通り。

1. `source_ref` dict 化を完了する。
2. PDF bbox 改善を完了する。
3. scope別Gemini入力を整理する。
4. XLSX / DOCX anchor を整理する。
5. document routing を入れる。
6. retry run の状態設計を入れる。
7. `bbox_retry` を入れる。
8. `scope_retry` を入れる。
9. `review_retry` を入れる。

最初に実装する retry は `bbox_retry` がよい。理由は、`case_data` を触らず、human edit 上書きリスクが最も低いため。
