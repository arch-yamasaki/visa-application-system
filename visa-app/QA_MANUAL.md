# QA手順

## 起動

ターミナル1: `cd visa-app/frontend && npm run dev`
ターミナル2: `cd visa-app/backend && uvicorn main:app --reload --port 8080`

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
curl -X POST http://localhost:8080/cases/{case_id}/extract
```

ボディ不要（デフォルト: gemini + auto）。既存の case_data/field_metadata/review は全上書き。

## 確認ポイント

- [ ] バッジ: 問題なしフィールドはバッジなし、要対応のみオレンジ表示
- [ ] ハイライト: フィールドクリックで該当セルのみハイライト（複数ハイライトされない）
- [ ] 雇用条件: employment_conditions セクションにフィールドが表示される
- [ ] 証跡: source_refs がある場合、ドキュメントビューアに証跡表示
- [ ] PDFハイライト: bbox 座標でのハイライト表示

## Playwright E2E

```bash
cd visa-app/frontend && npx playwright test
```
