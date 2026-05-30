# Real Data QA 2026-05-31

## 対象

`source_ref` dict化、PDF bbox、scope別Gemini入力の実データ確認。

## 環境

| 項目 | 値 |
|---|---|
| Backend | local FastAPI `http://127.0.0.1:8080` |
| Frontend | local Vite `http://127.0.0.1:5173` |
| Python | `visa-app/backend/.venv/bin/python` |
| GCP project | `visa-codex-mvp` |
| Gemini model | `gemini-3-flash-preview` |
| Thinking | `LOW` |

## 入力データ

restricted test data のため、ファイル実体は `qa/test-files/visa-test-amit_tamang/` にローカル配置。

| 種類 | 件数 |
|---|---:|
| DOCX | 1 |
| PDF | 2 |
| XLSX | 1 |

## 実行コマンド

```bash
cd visa-app/backend
.venv/bin/python -m pytest -q

.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8080
```

```bash
cd visa-app/frontend
npm run dev -- --host 127.0.0.1
```

抽出はAPIで新規case作成、4ファイルupload、`POST /cases/{case_id}/extract-stream` を実行した。

## 結果

| 確認 | 結果 |
|---|---|
| backend unit test | `108 passed` |
| frontend build | OK |
| case id | `case_4bb5af49afcd` |
| workflow_state | `extracted` |
| 抽出時間 | 約45.8秒 |
| Gemini scope | `applicant_identity`, `entry_plan`, `immigration_history`, `education`, `employment_history`, `employer`, `employment`, `review` |
| failed scopes | 0 |
| field_metadata | 72 fields |
| source_refs | 57 refs |
| PDF bbox | 24 refs |
| document_id欠落 | 0 refs |
| application-data | 53 rows |

## 抽出内容のスポット確認

| 項目 | 結果 |
|---|---|
| 国籍・地域 | 抽出済み |
| 生年月日 | 抽出済み |
| 旅券番号 / 有効期限 | 抽出済み |
| 同伴者の有無 | `無` |
| 過去の出入国歴 | `無`, 回数 `0` |
| 在留資格認定証明書申請歴 | `無`, 回数 `0` |
| 犯罪歴 | `無` |
| 入国予定日 | 抽出済み |
| 上陸予定港 | `成田` |
| 希望期間 | 年 `5`, 月 `0` |
| 査証申請予定地 | 抽出済み |
| 最終学歴 | 抽出済み |
| 所属機関 | 抽出済み |
| 法人番号有無 / 法人番号 | 抽出済み |
| 年間売上 / 従業員数 | 抽出済み |
| 契約形態 | `雇用` |
| 月額給与 | 抽出済み |

## 保存形式の確認

- `canonical_case_data` / `case_data` に `source`, `source_ref`, `source_refs` は混入していない。
- 証跡は `field_metadata.{canonical_path}.source_refs[]` に保存されている。
- Gemini raw response は `{ value, source_ref }` で受け、backendで `source_refs[]` に正規化されている。
- PDF由来の一部 `source_refs` に `bbox` が付与されている。

## Frontend確認

Chrome DevToolsで `http://127.0.0.1:5173` を確認。

| 画面 | 結果 |
|---|---|
| 案件一覧 | `case_4bb5af49afcd` が表示される |
| 案件一覧 | 表示名、申請人、所属機関が表示される |
| レビュー画面 | RASENS順の項目が表示される |
| PDF証跡 | 月額給与クリックでPDFタブに切り替わり、bboxハイライトが表示される |
| Console | error / warning なし |
| Network | `/api/cases`, `/api/cases/{case_id}`, PDF content が 200 |

Build確認:

```bash
cd visa-app/frontend
npm run build
```

## 気づき

- 実データでは `source_ref` dict化とscope分割は動作している。
- PDF bboxは全証跡ではなくPDF証跡の一部に付与される。今回の確認では `source_refs` 57件中、bbox付きは24件。
- DOCX / XLSX は現時点ではbboxではなく `text_quote` ベースのハイライト導線。
- `proxy` は抽出対象ではなく、表示側で所属機関情報から代理人表示を作っている。
- `intermediary` 固定値は今回のcaseでは未入力。固定データの保存・初期表示は別タスクで確認する。

## 判定

01〜03の主目的は実データで確認できた。

- `source_ref` dict化: OK
- scope別Gemini抽出: OK
- PDF bbox事前抽出: 部分OK
- frontend review導線: OK

次に進むなら、04 XLSX cell anchor と 05 DOCX block anchor で Office系の証跡精度を上げる。
