# 実データ抽出フロー

この文書は、visa-app がアップロード済み書類を Gemini で読み取り、レビュー画面へ渡すまでの現在の処理順を説明します。

## 1. 画面側の起点

ユーザーが UploadPage で「抽出開始」を押します。

Gemini が選ばれている場合、frontend は `/cases/{case_id}/extract-stream` に POST し、SSE で進捗を受け取ります。

画面側の流れ:

1. `extracting=true` にする。
2. `/extract-stream` を呼ぶ。
3. backend から `downloading` を受け取る。
4. backend から `extracting` を受け取る。
5. backend から `saving` を受け取る。
6. `complete` を受け取ったら ReviewPage へ遷移する。
7. `error` または stream 中断なら失敗表示にする。

Codex が選ばれている場合は `/extract` を呼び、`/extraction-status` を poll します。

## 2. `/extract-stream`

Gemini の通常画面フローは `backend/main.py` の `/cases/{case_id}/extract-stream` が入口です。

処理順:

1. Firestore から case を読む。
2. `document_manifest.documents` が空なら 400 を返す。
3. Firestore の `workflow_state` を `extracting` にする。
4. SSE で `downloading` を返す。
5. SSE で `extracting` を返す。
6. `_extract_with_gemini()` を同期実行する。
7. 抽出結果が空なら失敗扱いにする。
8. SSE で `saving` を返す。
9. Firestore に `case_data`, `review`, `field_metadata` を保存する。
10. Firestore の `workflow_state` を `extracted` にする。
11. SSE で `complete` を返す。

例外時は `workflow_state=failed` にします。stream中断時も `finally` で `extracting` に残らないようにします。

## 3. Gemini 前処理

`_extract_with_gemini()` は Gemini に渡す入力を準備します。

処理順:

1. case から document manifest を取得する。
2. `case_id`, `application_type`, `target_status` から case metadata を作る。
3. GCS から全アップロード書類を並列ダウンロードする。
4. 拡張子で分類する。

| 拡張子 | 処理 |
|---|---|
| PDF | Gemini に `application/pdf` として直接渡す |
| DOC/DOCX | backend 側でテキスト抽出して渡す |
| XLS/XLSX | backend 側でテキスト抽出して渡す |
| PNG/JPG/JPEG | Gemini に画像として渡す |

bbox locator はPDF由来の `source_refs` に対して事前実行します。`ENABLE_BBOX_LOCATOR=false` を明示した場合だけ無効化します。

## 4. scope 抽出

`extractors/gemini.py` の `extract_all_scopes()` が scope 抽出の本体です。

現在のscope:

| scope | 役割 |
|---|---|
| `identity` | 申請人基本情報、旅券、入国予定、出入国歴など |
| `employer` | 所属機関、雇用条件、活動内容 |
| `education` | 学歴、専攻、資格 |
| `review` | 抽出済みデータと原本の照合 |

処理順:

1. `identity`, `employer`, `education` を並列実行する。
2. 各scopeで `extract_scoped()` を呼ぶ。
3. `extract_scoped()` は scope 用 prompt と response schema を作る。
4. `_call_gemini()` が Gemini API を呼ぶ。
5. 成功したscope結果を deep merge して `merged_case_data` を作る。
6. `review` scope を実行する。
7. `_build_extraction_result()` で保存用形式に変換する。

一部scopeが失敗しても、成功scopeの結果は人間レビューで確認できるようにします。失敗scopeは `review.validation_errors` に明示します。

すべての主要scopeが失敗した場合だけ、抽出全体を `failed` とします。

## 5. 保存されるデータ

抽出後に保存する主なデータ:

| データ | 用途 |
|---|---|
| `case_data` | レビュー画面と `/application-data` の元データ |
| `field_metadata` | canonical path ごとの source_refs / confidence |
| `review` | 不足、矛盾、失敗scope、人手確認事項 |
| `workflow_state` | `draft`, `extracting`, `extracted`, `failed` |

`case_data` は value-only の canonical data です。根拠は `field_metadata` に分けます。

内部処理と保存後では、`case_data` の形が違います。

| 段階 | `case_data` の形 | 根拠の持ち方 | 主に見る人 |
|---|---|---|---|
| Gemini出力直後 | `{ value, source }` 付き | 各fieldの中に source がある | backend |
| 正規化後 | `{ value, source_refs }` 付き | 各fieldの中に source_refs がある | backend |
| Firestore保存後 | value-only | `field_metadata` に分離 | レビュー画面、人間 |
| Chrome拡張向け | application rows | mapping と `field_metadata` を参照可能 | 拡張、RASENS入力 |

人間レビューで見る `case_data` は、入力しやすい value-only の値です。原本根拠や confidence は `field_metadata` に分けることで、フォーム入力データと証跡データが混ざらないようにします。

## 6. `/extract` との違い

`/extract-stream` は Gemini 用の SSE 同期抽出です。通常画面の Gemini 抽出はこちらを使います。

`/extract` は backend 選択によって分岐します。

| backend | 処理 |
|---|---|
| `gemini` | `_start_gemini_extraction()` を同期実行。SSE progress は返さない |
| `codex` | Cloud Run Job を起動し、`extraction_session_id` を保存する |

そのため、Gemini SSE フローで `extraction_session_id=null` なのは異常ではありません。

## 7. Gemini API 制約として見るべき点

公式docs上、Gemini の入力・出力はテキストだけでなく PDF や画像も token として数えられます。`count_tokens` と `response.usage_metadata` で token 数を確認できます。

structured output は JSON Schema の subset を使います。schemaが大きい、深い、制約が多い場合は、schemaを単純化することが推奨されています。

現在のコードは `max_output_tokens=65536` で、ローカル確認でも `gemini-3-flash-preview`, `gemini-3.5-flash`, `gemini-2.5-flash` の `output_token_limit` は 65536 でした。したがって、単純に設定値が小さすぎる可能性は低いです。

一方で、全フィールドに `value + source` を必須で返させるため、出力JSONは大きくなります。`finish_reason=MAX_TOKENS` や usage metadata はログで確認します。

## 8. 実ケースで見る処理フロー

実データでは、値そのものではなく「件数・状態・pathの有無」で処理が進んだかを見ます。

例: 4書類をアップロードしたケース

| 段階 | 見るもの | 期待する状態 |
|---|---|---|
| upload完了 | `document_manifest.documents` | 4件ある |
| stream開始 | `extract_metric event=stream_started` | `run_id` が発行される |
| GCS download | `extract_metric event=document_downloaded` | documentごとに `ext`, `bytes`, `elapsed_ms` が出る |
| 前処理完了 | `documents_download_complete` | `files=4`, `total_bytes` が出る |
| text抽出 | `document_text_extracted` | docx/xlsx は `text_chars`, `pages` が出る |
| Gemini入力 | `scope_input_built` | `identity`, `employer`, `education`, `review` の parts/documents が出る |
| Gemini呼び出し | `gemini_metric event=request_start/request_complete` | scope別の `elapsed_ms` が出る |
| token確認 | `gemini_metric event=token_usage` | `prompt_tokens`, `candidate_tokens`, `total_tokens` が出る |
| 保存 | `firestore_state_updated` | `workflow_state=extracted` になる |
| UI完了 | `ui.extract.complete` | 同じ `run_id` で complete が出る |

このケースで途中失敗している場合でも、成功scopeの `case_data` はレビュー画面で確認できるようにします。失敗scopeは `review.validation_errors` に残し、全主要scopeが失敗した場合だけ `failed` にします。

実ケースを1件読むときの見方:

| 観点 | 例 | 意味 |
|---|---|---|
| `uploaded_documents` | 4 | アップロード自体は完了している |
| `processed_documents` | 4 | 抽出処理に渡せた |
| `completed_scopes` | 2 | 一部のscopeは成功している |
| `failed_scopes` | 1 | 失敗scopeはレビューで確認する |
| `case_data roots` | `applicant`, `employer`, `employment` | 取れた情報の大枠 |
| `workflow_state` | `extracted` | 抽出結果をレビュー画面で確認・編集できる |
| `/application-data.fillable` | `true` | Chrome拡張でpreview / 入力できる |

`extracted` は「完全にOK」ではなく、「人間が確認できる材料が保存された」状態です。MVPではレビュー確認を状態として分けず、レビュー画面で編集して保存する運用にします。

## 9. 現行ルーティングと将来ルーティング

現行実装は、書類の中身を完全分類してからscopeに渡しているわけではありません。まず拡張子で処理方法を決め、その後にファイル名のヒューリスティックで一部scopeから会社系書類を除外します。

| 段階 | 現行 | 将来 |
|---|---|---|
| 処理方法 | 拡張子で PDF / docx / xlsx / image を分ける | 同じ |
| scope投入 | `identity` / `education` では会社系らしいファイル名を除外 | `document_role` または自動分類結果で決める |
| 失敗時の見方 | `scope_input_built` の documents/parts を見る | 分類結果とscope投入理由を見る |

root欠落が起きたときは、まず `scope_input_built` で対象scopeに何件渡ったかを見ます。将来的には、ファイル名推測ではなく書類タイプを明示したルーティングに寄せます。

## 10. 遅い原因を切り分けるログ

1回の抽出には `run_id` が付きます。backend log、Gemini log、frontend console log はこの `run_id` でつなげて確認します。

| 疑う場所 | 典型的な見え方 | 次に見るもの |
|---|---|---|
| GCS download | `document_downloaded` が遅い、または欠ける | GCSアクセス、ファイルサイズ、ネットワーク |
| docx/xlsx text抽出 | `document_text_extracted.elapsed_ms` が大きい | 該当拡張子、ページ数、text_chars |
| Gemini入力が大きい | `scope_input_built.parts/documents` が多い | scope別の文書ルーティング |
| Gemini待ち | `request_start` から `request_complete` までが長い | scope、prompt_tokens、total_tokens |
| 出力が大きい | `candidate_tokens` が大きい、`finish_reason=MAX_TOKENS` | schemaのrequired数、source出力量 |
| JSON処理 | `response_parsed.elapsed_ms` が大きい、parse error | response_chars、json_repair有無 |
| 保存 | `stream_completed` が出る前に止まる | Firestore update、workflow_state |
| UI/SSE | backendは完了しているがUIが失敗 | `ui.extract.*` と `stream_closed_without_finish` |

判断の基本は「最後に出た `run_id` 付きログがどこか」です。最後が `scope_input_built` なら Gemini呼び出し前後、最後が `request_start` ならモデル応答待ち、最後が `stream_completed` ならUI/SSE側を疑います。
