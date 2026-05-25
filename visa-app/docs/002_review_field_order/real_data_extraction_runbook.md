# 実データ抽出 runbook

このメモは、実案件書類を Gemini で抽出するときの確認手順と成功判定を定義します。

PIIを含む値そのものではなく、件数、scope、状態、path の有無で確認します。

## 方針

実データ抽出は、次の工程に分けて扱います。

1. 書類から canonical `case_data` / `field_metadata` / `review` を作る。
2. レビュー画面で不足・矛盾・手入力項目を確認する。
3. レビュー完了後に `/application-data` rows を生成し、Chrome拡張へ渡す。
4. PDF由来の根拠について bbox を事前取得し、証跡ハイライトを改善する。

bbox取得は値抽出の成功条件に含めません。bboxが遅い、または失敗しても、値抽出結果を保存できる設計にします。`ENABLE_BBOX_LOCATOR=false` を明示した場合だけ bbox 事前取得を止めます。

## 成功条件

抽出成功とみなす条件:

- `/extract-stream` が `complete` を返す。
- Firestore の `workflow_state` が `needs_review` になる。
- 3主要scopeのうち1つ以上が成功している。
- `case_data` が canonical v2 の path だけで構成されている。
- `field_metadata` key が canonical path と一致している。
- `review` が不足・矛盾・確認事項を表現できる形式になっている。

partial extraction は `ready_to_fill` 扱いにしません。ただし、成功scopeの結果は人間レビューで確認できるように保存します。失敗scopeは `review.validation_errors` に明示します。

## 確認指標

QAでは次を確認します。

| 指標 | 意味 |
|---|---|
| `uploaded_documents` | アップロード済み書類数 |
| `processed_documents` | 抽出に渡した書類数 |
| `completed_scopes` | 成功した抽出scope。現状はログと review で確認 |
| `failed_scopes` | 失敗した抽出scope。現状は `review.validation_errors` で確認 |
| `case_data` root | canonical root の有無 |
| `field_metadata_count` | 根拠付き項目数 |
| `review_missing_count` | 不足項目数 |
| `review_validation_error_count` | 矛盾・検証エラー数 |
| `duration_sec` | 抽出時間 |
| `gemini_error_type` | timeout, quota, invalid_json など |

## 実ケースQA例

実案件の値はログやドキュメントに残さず、次の粒度で確認します。

| 項目 | 例 |
|---|---|
| case | 実データ検証用の1ケース |
| アップロード済み書類 | 4件 |
| 書類種別 | docx 1件、pdf 2件、xlsx 1件 |
| 抽出方式 | Gemini SSE (`/extract-stream`) |
| `extraction_session_id` | Gemini SSEでは通常 `null` |
| 保存先 | Firestore `cases/{case_id}` |
| レビュー画面の入口 | `workflow_state=needs_review` |

抽出後に見るFirestoreの形:

| データ | 確認観点 |
|---|---|
| `case_data` | canonical root が想定通りにあるか |
| `field_metadata` | key が canonical path と一致しているか |
| `review.missing_items` | 不足情報がレビュー可能に出ているか |
| `review.validation_errors` | scope失敗や矛盾が残っているか |
| `workflow_state` | `needs_review` か `extraction_failed` か |

この例では、一部の root だけが保存されている状態は「全失敗」ではありません。成功したscopeの情報をレビュー画面で見られるなら、次に見るべきは `review.validation_errors` と `scope_input_built` / `gemini_metric` の対応です。

## ログでの調査手順

抽出1回ごとに `run_id` を使って追跡します。

1. frontend console の `ui.extract.fetch_started` で開始を確認する。
2. backend log の `extract_metric event=stream_started` で同じ `run_id` を確認する。
3. `document_downloaded` と `documents_download_complete` でGCS downloadを確認する。
4. `document_text_extracted` でdocx/xlsxのtext化を確認する。
5. `scope_input_built` でscopeごとの入力量を確認する。
6. `gemini_metric event=token_usage` で入力・出力tokenを確認する。
7. `firestore_state_updated` と `stream_completed` で保存完了を確認する。
8. UI側の `ui.extract.complete` まで同じ `run_id` でつながるか確認する。

最後に出たログで原因候補を絞ります。

| 最後に出たログ | 原因候補 |
|---|---|
| `document_downloaded` の途中 | GCS download、ファイルサイズ、権限 |
| `document_text_extracted` の途中 | docx/xlsx parsing |
| `scope_input_built` | Gemini呼び出し直前または並列scope開始 |
| `request_start` | Gemini応答待ち、timeout、quota、モデル側遅延 |
| `token_usage` の後 | JSON parse、review scope、Firestore保存 |
| `stream_completed` の後 | frontend/SSE受信、画面遷移 |

## 内部データと保存後データ

Geminiから返るデータと、レビュー画面が見るデータは同じ名前でも形が違います。

| 段階 | データの形 | 根拠 |
|---|---|---|
| Gemini出力 | fieldごとに `value` と `source` を持つ | field内部 |
| backend正規化 | fieldごとに `value` と `source_refs` を持つ | field内部 |
| Firestore保存 | `case_data` は値だけ | `field_metadata` に分離 |
| application-data | RASENS入力用 rows | `case_data` と mapping から生成 |

QAで `case_data` を見るときは「入力値の大枠」、`field_metadata` を見るときは「根拠の有無」、`review` を見るときは「人間確認が必要な理由」と分けて確認します。

## 1件のケースをどう読むか

非エンジニア向けには、次の1表で現在地を判断します。

| 観点 | 例 | 判断 |
|---|---|---|
| upload | 4書類 | 読み取り対象は揃っている |
| processed | 4書類 | backend処理に渡せている |
| completed scopes | 2 | 取れた範囲はレビューできる |
| failed scopes | 1 | 不足scopeを人間が確認する |
| `case_data` roots | `applicant`, `employer`, `employment` | どの大枠が取れたか |
| state | `needs_review` | 自動入力前のレビュー段階 |
| fillable | `false` | Chrome拡張で本入力しない |

この状態は「失敗」ではなく「レビュー可能な途中結果」です。全主要scopeが失敗した場合だけ `extraction_failed` として扱います。

## scope と文書ルーティング

全書類を全scopeに渡すと、遅延、timeout、誤抽出、source ref のずれが起きやすくなります。

MVPでは、まず次の方針でscopeごとに渡す文書を絞ります。

| scope | 主な対象 | 渡す文書の例 |
|---|---|---|
| `identity` | 申請人基本情報、旅券、入国予定、出入国歴 | 申請書、旅券、申請人情報シート |
| `employer` | 所属機関、契約、活動内容 | 雇用条件通知書、会社書類 |
| `education` | 学歴、専攻、資格 | 卒業証明書、成績証明書、履歴書 |
| `review` | 不足・矛盾・確認事項 | 抽出済みcase_dataと必要書類 |

将来的には、ファイル名推測ではなく `document_role` または自動分類結果を使ってルーティングします。

## Chrome拡張へ渡せる条件

`/application-data` は `ready_to_fill` のケースだけを自動入力可能にします。

`ready_to_fill` に進める条件:

- 抽出が complete している。
- レビュー必須項目が確認済み。
- MVP mapping 対象の required 値が空でない。
- 固定値・設定値を注入できる。
- `/application-data` の warning に blocker がない。

`needs_review` や `extraction_failed` のケースは preview 用に rows を返すことはあっても、`fillable=false` にします。

## 失敗時の切り分け

| 状態 | 見る場所 |
|---|---|
| `extracting` のまま | `/extract-stream` の中断、Gemini timeout、backend reload |
| `field_metadata` が増えない | GCS download、Gemini認証、Gemini API timeout |
| rootが一部だけ | scope失敗、schema不足、文書ルーティング不備。レビューで確認できるよう失敗scopeを表示する |
| rowsが少ない | mapping対象pathが `case_data` にない |
| `fillable=false` | `workflow_state`, warning, review未完了 |
