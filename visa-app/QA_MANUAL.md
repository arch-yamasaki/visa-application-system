# QA手順

## 起動

ターミナル1: `cd visa-app/frontend && npm run dev`
ターミナル2: `cd visa-app/backend && .venv/bin/python -m uvicorn main:app --reload --port 8080`

backend のPythonコマンドは project-local venv を使う。

```bash
cd visa-app/backend
.venv/bin/python -m pytest -q
```

## テスト用ファイル

`qa/test-files/` に以下の4ファイルを配置（git管理外）：

| ファイル | 形式 | 内容 |
|---|---|---|
| `20250527オファーレター_No9_Amit Tamang.pdf` | PDF | オファーレター原本 |
| `20250508_オファーレター（日本語自動翻訳版）.docx` | DOCX | オファーレター日本語翻訳 |
| `会社書類.pdf` | PDF | 会社登記書類 |
| `中央ビジネスグループ御中_株式会社フジタ様内定者8名のCOE書類.xlsx` | XLSX | 申請人情報一覧 |

対応形式は `.pdf`, `.docx`, `.xlsx`, `.png`, `.jpg`, `.jpeg`。旧Office形式（`.doc`, `.xls`）やTIFFなどはアップロード時点で拒否またはスキップされることを確認する。

## 手動QAフロー

1. http://localhost:5173 を開く
2. 「+ 新規案件」でケース作成
3. 上記4ファイルをアップロード
4. 「Gemini」で抽出実行
5. レビュー画面で確認

スクリーンショットは `qa/screenshots/<YYYY-MM-DD>/` に保存する。ルート直下には画像ファイルを置かない。

## 再抽出（API）

```bash
curl -N -X POST http://localhost:8080/cases/{case_id}/extract-stream \
  -H 'Content-Type: application/json' \
  -d '{"backend":"gemini","pattern":"auto","scoped":true}'
```

`extract-stream` はSSEで進捗を返す。抽出結果は既存の `case_data` に merge され、`case.*`, `proxy`, `receiving_method` など抽出対象外の保存データを残す。

## 抽出失敗時の確認

Gemini API key が無効、権限不足、漏洩報告済みの場合は、抽出品質の問題ではなく環境設定の問題として扱う。画面には失敗した進捗行と、`GOOGLE_API_KEY` の差し替えや権限確認が必要だと分かるメッセージが表示されることを確認する。

SSE が完了イベントを受け取る前に切断された場合は、frontend が最新のケース状態を再取得する。backend 側で `workflow_state=extracted` になっていればレビュー画面へ進み、`failed` の場合だけ失敗として表示する。

## 確認ポイント

- [ ] バッジ: 問題なしフィールドはバッジなし、要対応のみオレンジ表示
- [ ] ハイライト: フィールドクリックで該当セルのみハイライト（複数ハイライトされない）
- [ ] canonical v2: 旧path（`application.*`, top-level `passport.*`, `employment_conditions.*`）が表示・保存されない
- [ ] 雇用条件: `employment` セクションに契約形態、給与、活動内容詳細が表示される
- [ ] 旅券: `applicant.passport.number` / `applicant.passport.expiry_date` が表示される
- [ ] 入国目的: `entry_plan.purpose_of_entry` が表示される
- [ ] 証跡: source_refs がある場合、ドキュメントビューアに証跡表示
- [ ] PDFハイライト: bbox 座標でのハイライト表示
- [ ] 位置候補: 同じ証跡文字列が複数位置にある場合、FieldRow に `位置候補N` が出て、PDFビューア側の候補ナビで移動できる
- [ ] 値候補: 値が食い違うフィールドに `別候補N` が出る。展開すると現在値・別候補・書類名・ページ・quoteが表示される
- [ ] 値候補: 別候補クリックで該当証跡へジャンプし、`採用` で表示値が置き換わる。保存後も `field_metadata.alternatives` は残る
- [ ] source_ref: Gemini raw response は `{ value, source_ref }`、保存後は `field_metadata.*.source_refs[]`
- [ ] alternatives: Gemini raw response は値が食い違う場合のみ `{ value, source_ref, alternatives: [{ value, source_ref }] }`。同値や表記ゆれだけの候補は入らない
- [ ] source_ref: `case_data` に `source`, `source_ref`, `source_refs` が混入しない
- [ ] alternatives: `case_data` に `alternatives` が混入せず、候補は `field_metadata.*.alternatives[]` にだけ保存される
- [ ] scope: `applicant_identity`, `entry_plan`, `immigration_history`, `education`, `employment_history`, `employer`, `employment`, `review` がエラーなく完了
- [ ] Gemini auth error: API key 無効、権限不足、漏洩報告済みは一般的な「再試行してください」ではなく、環境設定エラーとして表示される
- [ ] extract-stream: 完了イベント前にSSEが閉じても、ケース状態を再取得して `extracted` / `failed` の表示がbackendと一致する
- [ ] unsupported files: `.doc`, `.xls`, `.tif`, `.txt` など未対応形式は保存されず、画面またはAPIで理由が分かる
- [ ] xlsx preview: 存在しない `sheet` パラメータは 500 ではなく 400 を返す
- [ ] application-data: `/cases/{case_id}/application-data` が `rows`, `fillable`, `warnings` を返す
- [ ] Chrome DevTools MCP: 実画面でレビュー画面、PDF bbox、Network/Consoleを確認する

Chrome DevTools MCP の共通手順は `../docs/shared/chrome_devtools_mcp_qa.md` を参照。
