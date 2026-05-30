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

## 手動QAフロー

1. http://localhost:5173 を開く
2. 「+ 新規案件」でケース作成
3. 上記4ファイルをアップロード
4. 「Gemini」で抽出実行
5. レビュー画面で確認

## 再抽出（API）

```bash
curl -N -X POST http://localhost:8080/cases/{case_id}/extract-stream \
  -H 'Content-Type: application/json' \
  -d '{"backend":"gemini","pattern":"auto","scoped":true}'
```

`extract-stream` はSSEで進捗を返す。抽出結果は既存の `case_data` に merge され、`case.*`, `proxy`, `receiving_method` など抽出対象外の保存データを残す。

## 確認ポイント

- [ ] バッジ: 問題なしフィールドはバッジなし、要対応のみオレンジ表示
- [ ] ハイライト: フィールドクリックで該当セルのみハイライト（複数ハイライトされない）
- [ ] canonical v2: 旧path（`application.*`, top-level `passport.*`, `employment_conditions.*`）が表示・保存されない
- [ ] 雇用条件: `employment` セクションに契約形態、給与、活動内容詳細が表示される
- [ ] 旅券: `applicant.passport.number` / `applicant.passport.expiry_date` が表示される
- [ ] 入国目的: `entry_plan.purpose_of_entry` が表示される
- [ ] 証跡: source_refs がある場合、ドキュメントビューアに証跡表示
- [ ] PDFハイライト: bbox 座標でのハイライト表示
- [ ] source_ref: Gemini raw response は `{ value, source_ref }`、保存後は `field_metadata.*.source_refs[]`
- [ ] source_ref: `case_data` に `source`, `source_ref`, `source_refs` が混入しない
- [ ] scope: `applicant_identity`, `entry_plan`, `immigration_history`, `education`, `employment_history`, `employer`, `employment`, `review` がエラーなく完了
- [ ] application-data: `/cases/{case_id}/application-data` が `rows`, `fillable`, `warnings` を返す
- [ ] Chrome DevTools MCP: 実画面でレビュー画面、PDF bbox、Network/Consoleを確認する

Chrome DevTools MCP の共通手順は `../docs/shared/chrome_devtools_mcp_qa.md` を参照。
