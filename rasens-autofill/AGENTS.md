# rasens-autofill

Chrome拡張による在留申請オンラインシステム(RASENS)フォーム自動入力 + データパイプライン。

## ディレクトリ構成

```text
rasens-autofill/
  data/
    schemas/           # case_data, document_manifest, review の JSON Schema
    cases/             # 合成デモ・fixture用 case_data。実運用案件の正本ではない
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
    api_client.js      # visa-app API通信クライアント
    application_data.json  # 同梱デモ投入データ
  docs/
  reference/
  QA_POLICY.md
```

## 重要ファイル

- `docs/データ設計.md`: Firestore case_data / form_definitions / application_data の役割整理とフォルダ構成
- `docs/Chrome_DevTools_MCP_autoConnect.md`: DevTools MCP 接続手順
- `data/cases/demo_case_data.json`: 架空デモ案件の fixture。実運用案件の正本ではない
- `data/form_definitions/rasens_offer_fields.json`: フォーム全項目台帳の正本
- `data/mappings/rasens_offer_mapping_v2.json`: canonical v2 case_data からフォーム入力行への変換ルール
- `data/generated/demo_application_data.json`: デモ案件から生成した Chrome 拡張投入用 JSON
- `data/schemas/*.json`: case_data, document_manifest, review の JSON Schema 定義
- `extension/api_client.js`: visa-app API経由でautofillデータを取得するクライアント（Firestore直接参照から移行）
- `extension/`: Chrome拡張本体 (manifest.json, content.js, popup.html/js/css, api_client.js)
- `scripts/build_application_data.py`: case_data + mapping -> application_data を生成するスクリプト

## データフロー

Chrome拡張は visa-app API 経由で application-data を取得する。backend が canonical `case_data`、フォーム台帳、mapping v2、設定値から `rows` を生成し、拡張はその行をRASENS DOMへ入力する。

```
visa-app (Gemini/Codex抽出) → /cases/{case_id}/application-data → Chrome拡張 (api_client.js) → content.js → RASENSフォーム
```

Chrome拡張には `case_data`、mapping、`transform`、`visible_when` の解釈を持たせない。

## Chrome拡張の接続先設定

Chrome拡張のポップアップUI内「接続先設定」からAPI URLを設定する。`chrome.storage.local` に `visaAppApiUrl` として保存される。

- ローカル開発時: `http://localhost:8080`
- Cloud Run: `https://visa-app-913363513517.asia-northeast1.run.app`

未設定の場合は Cloud Run を使う。ローカル開発時だけ「接続先設定」で `http://localhost:8080` に上書きする。

## データ再生成

```bash
python3 scripts/build_application_data.py \
  data/cases/demo_case_data.json \
  data/mappings/rasens_offer_mapping_v2.json \
  data/generated/demo_application_data.json
```

## QAポリシー要点

- 申請の最終送信ボタンは絶対に押さない。入力確認・スクリーンショットまでに留める。
- 実PIIデータでQAする場合は専用Chromeプロファイルを使い、終了後に `chrome.storage.local` を消去する。
- バグ報告やチャット転記では氏名・住所・旅券番号等のPIIを伏せる。
- 実PII入りファイルをGitにコミットしない。詳細は `QA_POLICY.md` を参照。
