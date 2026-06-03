# 在留資格申請 AIエージェント支援 docs

このディレクトリは、2026-05-01 の業務ヒアリング内容をもとに、在留資格申請支援AIエージェントの業務理解・要件・実装方針をまとめるための場所です。

## ディレクトリ構成

共通ドキュメントは `docs/shared/` に置き、プロジェクト固有のドキュメントは各プロジェクトの `docs/` に置く。

### docs/shared/ (共通ドキュメント)

- `001_hearing_notes/`: ヒアリング原本と要約
  - [raw/2026-05-01_業務ヒアリング.txt](shared/001_hearing_notes/raw/2026-05-01_業務ヒアリング.txt)
  - [2026-05-01_ヒアリング要約.md](shared/001_hearing_notes/2026-05-01_ヒアリング要約.md)
- `002_mvp_design/`: 業務フローとMVP要件
  - [業務フロー.md](shared/002_mvp_design/業務フロー.md)
  - [AIエージェント要件.md](shared/002_mvp_design/AIエージェント要件.md)
- `006_ai_agent_infrastructure/`: 汎用AIエージェント基盤の調査
  - [README.md](shared/006_ai_agent_infrastructure/README.md)
- [chrome_devtools_mcp_qa.md](shared/chrome_devtools_mcp_qa.md): Chrome DevTools MCPでの実画面QA手順

### visa-eval/docs/

- [AIブラインド抽出実行手順.md](../visa-eval/docs/AIブラインド抽出実行手順.md): expected/goldenを見せずにAI抽出を実行する手順
- [manual_fixture_creation.md](../visa-eval/docs/manual_fixture_creation.md): eval fixtureを手動で作る手順。input/output分離とPDF分割方針
- [単票評価ワークフローまとめ.md](../visa-eval/docs/単票評価ワークフローまとめ.md): 単票fixture、expected、Chrome拡張投入までの全体像

### rasens-autofill/docs/

- [データ設計.md](../rasens-autofill/docs/データ設計.md): 正規case_data、フォーム台帳、投入用JSONの関係
- [Chrome_DevTools_MCP_autoConnect.md](../rasens-autofill/docs/Chrome_DevTools_MCP_autoConnect.md): Chrome拡張とブラウザ運用メモ

### visa-app/docs/

- [README.md](../visa-app/docs/README.md): visa-app の現行設計ドキュメント入口
- [006_current_architecture](../visa-app/docs/006_current_architecture/): 現行アーキテクチャ
- [001_codex_remote_execution](../visa-app/docs/001_codex_remote_execution/): Codex 実行基盤の設計

## データの正本と生成物

実運用のケース保存先は Firestore の `cases` コレクション。現行の `case_data` は `visa-app/docs/002_review_field_order/canonical_case_data_v2.md` を基準にし、Chrome拡張向けの物理フォーム行は backend が `/application-data` で生成する。

`rasens-autofill/data/cases/*case_data.json` はデモ・fixture用途であり、実運用案件の正本ではない。

フォーム項目の正本は `rasens-autofill/data/form_definitions/rasens_offer_fields.json`。在留申請オンラインシステムの `field_id`、`field_name`、選択肢、条件付き項目、繰り返し項目を保持する。

Chrome拡張へ渡す `application_data.json` は生成物。`case_data` と `mappings` から作る投入用データであり、案件管理の正本ではない。

テストデータは `visa-eval/test_cases_from_raw/` に置く。現行はまずAmit/Kushangの2ケースを手動整備し、申請人1人=1フォームの単票ケースとして、実PDF・Excelから `case_data`、`field_metadata`、`review` を作れるか検証する。旧ケース群は `visa-eval/archived/` に退避する。

`visa-eval/` は実案件由来のrestricted評価ワークスペース。git管理するのは `README.md` と `eval_config/suites/*.json` など実PIIを含まない説明・評価定義に限る。

## 現時点の結論

最初に狙うべき主対象は「技術・人文知識・国際業務」、通称「技人国」。ヒアリング上、フォースバレー経由の案件はほぼ技人国で、書類の型も比較的そろいやすい。AIエージェント化するなら、まず技人国の書類収集、項目抽出、不足確認、整合性チェック、申請フォーム入力支援から始めるのが現実的。

高度専門職、技能、興行、特定技能、配偶者系なども出てくるが、初期MVPでは広げすぎない。特にコックは技人国ではなく技能に寄る、芸能・出演系は興行に寄るなど、技人国から外れる分類は人の確認に回す。

## 重要な前提

- 申請の入口は、外国人本人、雇用会社、人材紹介会社、事業協同組合、士業・弁護士紹介など複数ある。
- フォースバレー経由は、申請人情報を紹介会社が持ち、雇用会社情報は雇用会社側から集める形になりやすい。
- フォースバレー以外は、履歴書、旅券、雇用条件通知書、卒業証明書、成績証明書などの品質がばらつくため、不足確認と再依頼が重要。
- 申請作成そのものは機械的な入力が多いが、「仕事内容と学歴・職歴がリンクしているか」「単純労働に見えないか」「活動内容詳細の表現が適切か」は人の判断が残る。
