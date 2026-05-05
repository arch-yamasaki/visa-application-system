# 在留資格申請 AIエージェント支援 docs

このディレクトリは、2026-05-01 の業務ヒアリング内容をもとに、在留資格申請支援AIエージェントの業務理解・要件・実装方針をまとめるための場所です。

## 元データ

- [001_hearing_notes/raw/2026-05-01_業務ヒアリング.txt](001_hearing_notes/raw/2026-05-01_業務ヒアリング.txt)

## まとめ

- [001_hearing_notes/2026-05-01_ヒアリング要約.md](001_hearing_notes/2026-05-01_ヒアリング要約.md)
- [002_mvp_design/業務フロー.md](002_mvp_design/業務フロー.md)
- [002_mvp_design/AIエージェント要件.md](002_mvp_design/AIエージェント要件.md)
- [003_data_and_testing/データ設計.md](003_data_and_testing/データ設計.md)
- [003_data_and_testing/テスト設計.md](003_data_and_testing/テスト設計.md)
- [004_chrome_extension_ops/Chrome_DevTools_MCP_autoConnect.md](004_chrome_extension_ops/Chrome_DevTools_MCP_autoConnect.md)
- [005_codex_remote_execution/README.md](005_codex_remote_execution/README.md)
- [006_ai_agent_infrastructure/README.md](006_ai_agent_infrastructure/README.md)

## ディレクトリ方針

- `001_hearing_notes`: ヒアリング原本と要約
- `002_mvp_design`: 業務フローとMVP要件
- `003_data_and_testing`: データ設計とテスト設計
- `004_chrome_extension_ops`: Chrome拡張とブラウザ運用メモ
- `005_codex_remote_execution`: Codex 実行基盤の設計
- `006_ai_agent_infrastructure`: 汎用AIエージェント基盤の調査

## データの正本と生成物

案件の正本は `visa_application_app/data/cases/*case_data.json`。OCR、ヒアリング、人手補正、レビュー状態、根拠資料はここに寄せる。

フォーム項目の正本は `visa_application_app/data/form_definitions/rasens_offer_fields.json`。在留申請オンラインシステムの `field_id`、`field_name`、選択肢、条件付き項目、繰り返し項目を保持する。

Chrome拡張へ渡す `application_data.json` は生成物。`case_data` と `mappings` から作る投入用データであり、案件管理の正本ではない。

テストデータは `visa_application_app/data/test_cases/fixtures/` と `visa_application_app/data/test_cases/fixtures_single/` に分ける。`fixtures/` は複数申請人を含むバッチケースの抽出・正規化テスト、`fixtures_single/` は申請人1人=1フォームの単票生成テストに使う。

## 現時点の結論

最初に狙うべき主対象は「技術・人文知識・国際業務」、通称「技人国」。ヒアリング上、フォースバレー経由の案件はほぼ技人国で、書類の型も比較的そろいやすい。AIエージェント化するなら、まず技人国の書類収集、項目抽出、不足確認、整合性チェック、申請フォーム入力支援から始めるのが現実的。

高度専門職、技能、興行、特定技能、配偶者系なども出てくるが、初期MVPでは広げすぎない。特にコックは技人国ではなく技能に寄る、芸能・出演系は興行に寄るなど、技人国から外れる分類は人の確認に回す。

## 重要な前提

- 申請の入口は、外国人本人、雇用会社、人材紹介会社、事業協同組合、士業・弁護士紹介など複数ある。
- フォースバレー経由は、申請人情報を紹介会社が持ち、雇用会社情報は雇用会社側から集める形になりやすい。
- フォースバレー以外は、履歴書、旅券、雇用条件通知書、卒業証明書、成績証明書などの品質がばらつくため、不足確認と再依頼が重要。
- 申請作成そのものは機械的な入力が多いが、「仕事内容と学歴・職歴がリンクしているか」「単純労働に見えないか」「活動内容詳細の表現が適切か」は人の判断が残る。
