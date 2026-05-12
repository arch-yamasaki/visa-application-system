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
| `rasens-autofill/` | rasens-autofill | Chrome拡張によるフォーム自動入力、データ設計 |
| `visa-eval/` | visa-eval | 実資料読み取り評価、テスト設計 |
| `codex-cloud/` | codex-cloud | Codex実行基盤、Cloud Run Jobs |
| `docs/shared/` | (共通) | ヒアリング、MVP設計、AIエージェント基盤調査 |

## 重要ファイル

### 共通ドキュメント (docs/shared/)

- `docs/shared/001_hearing_notes/raw/2026-05-01_業務ヒアリング.txt`: 元のヒアリング transcript
- `docs/shared/001_hearing_notes/2026-05-01_ヒアリング要約.md`: 論点要約
- `docs/shared/002_mvp_design/業務フロー.md`: 実務フロー
- `docs/shared/002_mvp_design/AIエージェント要件.md`: AIエージェントのMVP要件
- `docs/shared/006_ai_agent_infrastructure/README.md`: 汎用AIエージェント基盤の調査

### rasens-autofill (rasens-autofill/)

- `rasens-autofill/docs/データ設計.md`: 正規case_data、フォーム台帳、投入用JSONの関係
- `rasens-autofill/docs/Chrome_DevTools_MCP_autoConnect.md`: Chrome拡張とブラウザ運用メモ
- `rasens-autofill/data/cases/demo_case_data.json`: 架空デモ案件の正本
- `rasens-autofill/data/form_definitions/rasens_offer_fields.json`: 在留申請オンラインシステムのフォーム項目台帳
- `rasens-autofill/data/mappings/rasens_offer_mapping.json`: 正規case_dataからフォーム項目への変換ルール
- `rasens-autofill/data/generated/demo_application_data.json`: デモ案件から生成したChrome拡張投入用JSON

### visa-eval (visa-eval/)

- `visa-eval/docs/テスト設計.md`: raw資料、input_documents、golden expected、generated出力のテスト構成
- `visa-eval/docs/単票評価ワークフローまとめ.md`: 単票fixture、expected、Chrome拡張投入までの全体像
- `visa-eval/docs/AIブラインド抽出実行手順.md`: expected/goldenを見せずにAI抽出を実行する手順
- `visa-eval/docs/フォルダ整理案.md`: fixtures_single、runs、evalの役割分担案
- `visa-eval/README.md`: Codex/AIエージェントで実資料読み取りテストをするための入口
- `visa-eval/eval/suites/*.json`: 共有可能な評価スイート定義

### codex-cloud (codex-cloud/)

- `codex-cloud/docs/README.md`: Codex 実行基盤の設計
- `codex-cloud/docs/option3_codex_exec_json_cloud_run_jobs.md`: Cloud Run Jobs 方式

## 開発時の注意

- 実務判断をAIだけで確定させない。初期は「OK / 要確認 / 人の判断必須」のようなレビュー前提にする。
- 入管の制度・運用は変わるため、公式資料や実務家の確認を前提にする。
- 申請人情報、旅券、在留カード、家族情報、給与、契約情報など個人情報を扱うため、ログ・保存先・共有範囲に注意する。
- `visa-eval/raw/`, `visa-eval/catalog.json`, `visa-eval/fixtures_single/<case_id>/` は実PIIを含む restricted test data としてローカル管理し、gitに入れない。
- `rasens-autofill/data/` は設計資産としてgit管理する。ただし一時CSV、PDF/画像キャプチャ、実案件由来データは入れない。
- まずは技人国で型を固め、周辺業務としてシャローム入力、社会保険・雇用保険、助成金に広げる。
