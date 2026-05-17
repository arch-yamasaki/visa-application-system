# AGENTS.md

このディレクトリは、在留資格申請業務をAIエージェントで支援するための調査・試作ワークスペース。

## 超概要

- 主対象は「技術・人文知識・国際業務」、通称「技人国」。
- 初期MVPは、技人国の書類収集、OCR、項目抽出、不足確認、整合性チェック、申請入力支援に絞る。
- フォースバレー経由の案件はほぼ技人国で、申請人情報が比較的まとまりやすい。
- フォースバレー以外は、履歴書、旅券、雇用条件通知書、卒業証明書、成績証明書などの品質がばらつくため、不足確認と再依頼が重要。
- 判断の核は、仕事内容と学歴・職歴・成績科目がつながっているか、単純労働に見えないか、活動内容詳細の表現が適切か。
- 高度専門職、技能、興行、配偶者系、家族滞在、特定技能などは、初期では検知して人に回す。

## プロジェクト構成

| ディレクトリ | プロジェクト名 | 概要 |
|---|---|---|
| `visa-app/` | visa-app | ビザ申請レビューアプリ（フロント+バックエンド+ジョブ統合） |
| `visa-app/frontend/` | (visa-app) | React UI — ケース管理・レビュー画面 |
| `visa-app/backend/` | (visa-app) | FastAPI — 抽出エンジン(Gemini/Codex)・API |
| `visa-app/jobs/codex-runner/` | (visa-app) | Cloud Run Job — Codex非同期実行コンテナ |
| `rasens-autofill/` | rasens-autofill | Chrome拡張によるフォーム自動入力、データ設計 |
| `visa-eval/` | visa-eval | 実資料読み取り評価、テスト設計 |
| `docs/shared/` | (共通) | ヒアリング、MVP設計、AIエージェント基盤調査 |

## 共通ドキュメント (docs/shared/)

- `docs/shared/001_hearing_notes/raw/2026-05-01_業務ヒアリング.txt`: 元のヒアリング transcript
- `docs/shared/001_hearing_notes/2026-05-01_ヒアリング要約.md`: 論点要約
- `docs/shared/002_mvp_design/業務フロー.md`: 実務フロー
- `docs/shared/002_mvp_design/AIエージェント要件.md`: AIエージェントのMVP要件
- `docs/shared/006_ai_agent_infrastructure/README.md`: 汎用AIエージェント基盤の調査

各プロジェクトの詳細は各ディレクトリの `AGENTS.md` を参照。

## 開発時の注意

- 実務判断をAIだけで確定させない。初期は「OK / 要確認 / 人の判断必須」のようなレビュー前提にする。
- 入管の制度・運用は変わるため、公式資料や実務家の確認を前提にする。
- 申請人情報、旅券、在留カード、家族情報、給与、契約情報など個人情報を扱うため、ログ・保存先・共有範囲に注意する。
- `visa-eval/raw/`, `visa-eval/catalog.json`, `visa-eval/test_cases_from_raw/<case_id>/` は実PIIを含む restricted test data としてローカル管理し、gitに入れない。
- `rasens-autofill/data/` は設計資産としてgit管理する。ただし一時CSV、PDF/画像キャプチャ、実案件由来データは入れない。
- まずは技人国で型を固め、周辺業務としてシャローム入力、社会保険・雇用保険、助成金に広げる。
- QA検証スクリーンショットやテスト入力ファイルは `qa/` 配下に集約する（`qa/screenshots/`, `qa/test-files/`）。git管理外。
- Playwright E2Eテストのコードは `visa-app/frontend/e2e/` に配置し、テスト成果物（test-results/, playwright-report/, .playwright-mcp/）はコミットしない。
