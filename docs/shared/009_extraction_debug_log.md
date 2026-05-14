# 009 extraction_failed デバッグログ

**日付**: 2026-05-14
**チーム**: extraction-debug
**メンバー**: engineer, pm, em

---

## 1. 問題の症状

- ユーザーがファイルをアップロードして「抽出開始」を押すと `extraction_failed` になる
- orchestrator ログでは POST /extract が 200 で返っている（エラーは200レスポンスの中に含まれている）
- テストファイル: ~/Desktop/visa-test-amit_tamang/ (PDF x2, xlsx, docx)

## 2. 調査経緯

| 時刻 | 担当 | 内容 |
|------|------|------|
| 2026-05-14 | engineer | 調査開始 |
| 2026-05-14 | engineer | 根本原因2件を特定、修正・curl検証完了 |
| 2026-05-14 | pm | デバッグログ作成、QA向けテスト手順送付 |
| 2026-05-14 | qa | 全テスト項目 PASS、E2E 18/18 passed、ビルド成功 |

## 3. 根本原因

**原因1: Cloud Vision API の 403 エラー**
- `pattern="auto"` でスキャンPDF（テキストレイヤーなし）の場合、Cloud Vision API 経由の OCR が実行される
- ADC の quota project 未設定により `403 SERVICE_DISABLED` が発生
- 200レスポンスの中にエラーが含まれていたため、表面上はリクエスト成功に見えていた

**原因2: case_data の KeyError**
- 1回目の抽出で Gemini の結果が `case_data` を上書き
- 元の `case_data.case` のネスト構造が消失
- 2回目以降に `KeyError: 'case'` が発生

## 4. 修正内容

1. **Cloud Vision 依存の排除**: Gemini が PDF を直接読めるため、`auto` を `pdf_direct` にデフォルト化し Cloud Vision API への依存を排除
2. **case_data 構造の互換対応**: `.get("case", case_data)` で元のネスト構造・上書き後の構造の両方に対応

**検証結果**: `curl -X POST .../extract -d '{"backend":"gemini","pattern":"auto"}'` → `{"status":"completed","workflow_state":"needs_review"}` (成功)

## 5. テスト手順（QA向け）

### 前提
- orchestrator が port 8080 で起動していること
- visa-reviewer (フロントエンド) が起動していること

### 手順

1. **新規案件の作成**
   - visa-reviewer のトップ画面から「新規案件作成」
   - 申請人名等を入力して作成

2. **ファイルアップロード**
   - 案件詳細画面でファイルをアップロード
   - テストファイル: ~/Desktop/visa-test-amit_tamang/ (PDF x2, xlsx, docx)
   - 各ファイルがアップロード済みとして表示されることを確認

3. **抽出開始 → レビュー遷移の確認**
   - 「抽出開始」ボタンを押す
   - ローディング表示が出ること
   - `extraction_failed` にならず、`needs_review` 状態に遷移すること

4. **確認ポイント**
   - ブラウザコンソールにエラーが出ていないこと
   - 抽出結果のフィールド（氏名、国籍、パスポート番号等）が表示されること
   - 2回目の抽出を実行しても `KeyError` にならないこと

---

## 6. QA結果（2026-05-14）

**結果: 全項目 PASS**

### A. 抽出フロー確認
- 新規案件作成 ✓
- 4ファイルアップロード（PDF x2, DOCX, XLSX）✓
- 抽出開始 → ローディング表示あり ✓
- extraction_failed にならず needs_review に遷移 ✓
- コンソールエラー 0件 ✓
- 抽出結果正常表示 ✓
  - 氏名: AMIT TAMANG, 国籍: NEPAL, パスポート: PA2789572
  - 学歴: TRIBHUVAN UNIVERSITY, Architectural Engineering
  - 雇用情報: フジタ, サイトエンジニア

### B. フォルダ一括アップロード
- 「フォルダを選択」ボタン表示 ✓

### 追加確認
- E2Eテスト: 18/18 passed ✓
- npm run build: 成功 ✓

### 注記
- Gender と職業が空欄 → ソース書類に記載なしのため妥当

---

## 7. 最終ステータス

**解決完了** (2026-05-14)

全タスク完了、QA全項目PASS。本件クローズ。

---

## 備考

- orchestrator: port 8080 で起動中 (--reload)
- GOOGLE_API_KEY: codex-cloud/orchestrator/.env に設定済み
