# rasens-autofill

Chrome拡張による在留申請オンラインシステム(RASENS)フォーム自動入力 + データパイプライン。

## ディレクトリ構成

```text
rasens-autofill/
  data/
    schemas/           # case_data, input_documents, review の JSON Schema
    cases/             # 案件単位の正規 case_data (正本)
    form_definitions/  # フォーム項目台帳 (rasens_offer_fields 等)
    mappings/          # case_data -> フォーム入力への変換ルール
    generated/         # Chrome拡張投入用 application_data (派生物)
    reference_form.html
  scripts/
    build_application_data.py   # case_data -> application_data 生成
    build_golden_from_intake.py # intake -> golden expected 生成
    classify_test_documents.py  # テスト資料分類
    prepare_blind_eval_run.py   # AIブラインド抽出の実行準備
  extension/
    manifest.json      # Chrome拡張マニフェスト
    content.js         # フォーム自動入力ロジック
    popup.html/js/css  # 拡張ポップアップUI
    application_data.json  # 同梱デモ投入データ
  docs/
  reference/
  QA_POLICY.md
```

## 重要ファイル

- `docs/データ設計.md`: case_data / form_definitions / application_data の3層設計とフォルダ構成
- `docs/Chrome_DevTools_MCP_autoConnect.md`: DevTools MCP 接続手順
- `data/cases/demo_case_data.json`: 架空デモ案件の正規データ (正本)
- `data/form_definitions/rasens_offer_fields.json`: フォーム全項目台帳の正本
- `data/mappings/rasens_offer_mapping.json`: 正規 case_data からフォーム入力行への変換ルール
- `data/generated/demo_application_data.json`: デモ案件から生成した Chrome 拡張投入用 JSON
- `data/schemas/*.json`: case_data, input_documents, review の JSON Schema 定義
- `extension/`: Chrome拡張本体 (manifest.json, content.js, popup.html/js/css)
- `scripts/build_application_data.py`: case_data + mapping -> application_data を生成するスクリプト

## データ再生成

```bash
python3 scripts/build_application_data.py \
  data/cases/demo_case_data.json \
  data/mappings/rasens_offer_mapping.json \
  data/generated/demo_application_data.json
```

## QAポリシー要点

- 申請の最終送信ボタンは絶対に押さない。入力確認・スクリーンショットまでに留める。
- 実PIIデータでQAする場合は専用Chromeプロファイルを使い、終了後に `chrome.storage.local` を消去する。
- バグ報告やチャット転記では氏名・住所・旅券番号等のPIIを伏せる。
- 実PII入りファイルをGitにコミットしない。詳細は `QA_POLICY.md` を参照。
