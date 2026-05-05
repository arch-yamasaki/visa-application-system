# Visa Application Autofill

在留申請オンラインシステムの入力ページで、同梱JSONの値をフォームに投入するChrome拡張です。

## 使い方

1. Chromeで `chrome://extensions/` を開く
2. 右上の「デベロッパー モード」を有効化
3. 「パッケージ化されていない拡張機能を読み込む」から、この `extension` フォルダを選択
4. 在留申請オンラインシステムの入力ページを開く
   - 対象URL例: `https://www.rasens-immi.moj.go.jp/rasens-u/offer/offerRSS_gotoOffer`
5. 拡張アイコンを押して「同梱データを使う」を実行
6. 「入力対象を確認」で件数を確認
7. 「一括入力」または「ゆっくり入力」を実行

## 入力モード

- `一括入力`: 対象項目をまとめて入力します。
- `ゆっくり入力`: 対象項目を順番に入力し、入力中の項目をハイライトして右下に進捗を表示します。

## データファイル

- `application_data.json`: 拡張に同梱するデモ/検証用の自動入力データ。案件正本ではありません。
- `../data/cases/demo_case_data.json`: 架空デモ案件の正規データ。
- `../data/generated/demo_application_data.json`: `demo_case_data.json` から生成した投入用JSON。
- `../data/form_definitions/rasens_offer_fields.json`: フォーム全項目台帳の正本。
- `../data/mappings/rasens_offer_mapping.json`: 正規データからフォーム入力行への変換ルール。

デモ投入JSONの再生成:

```bash
python3 ../scripts/build_application_data.py \
  ../data/cases/demo_case_data.json \
  ../data/mappings/rasens_offer_mapping.json \
  ../data/generated/demo_application_data.json
```

## 注意

この拡張およびQA作業では、申請の最終送信ボタンを絶対に押さないでください。入力後は確認・スクリーンショット・差分確認までに留め、送信が必要な場合は必ず人間が内容を最終確認してから手動で行ってください。

ファイル添付欄はChromeのセキュリティ制約で自動入力できません。顔写真と添付PDFは手動で選択してください。

同梱JSONの `confidence` が `medium` の行は、PDF画像のページ端やスクロールバーで一部隠れていたため、投入前に確認してください。

`Could not establish connection. Receiving end does not exist.` が出る場合は、対象ページにcontent scriptが入っていない状態です。拡張をリロードした後は対象ページもリロードしてください。この拡張は送信失敗時に `content.js` を再注入して再試行しますが、Chrome内部ページや対象外URLでは実行できません。
