# Visa Application Autofill

在留申請オンラインシステムの入力ページで、`application_data.rows` の値をフォームに投入するChrome拡張です。

canonical v2 移行後は、Chrome拡張は `case_data`、mapping、`transform`、`visible_when` を解釈しません。visa-app backend の `/cases/{case_id}/application-data` が生成した `rows` を受け取り、RASENS DOM に入力するだけの薄い責務にします。

## 使い方

1. Chromeで `chrome://extensions/` を開く
2. 右上の「デベロッパー モード」を有効化
3. 「パッケージ化されていない拡張機能を読み込む」から、この `extension` フォルダを選択
4. 在留申請オンラインシステムの入力ページを開く
   - 対象URL例: `https://www.rasens-immi.moj.go.jp/rasens-u/offer/offerRSS_gotoOffer`
5. 拡張アイコンを押すと `/cases` から案件一覧を取得します
6. 案件一覧 `select` から対象案件を選び、「visa-appから読込」を実行
   - 一覧を再取得したい場合は「更新」を押してください。
7. 「一括入力」を実行
   - RASENSタブが1つだけ開いていれば、そのタブへ接続します。
   - RASENSタブが複数ある場合は、入力したいタブをアクティブにしてから実行してください。
   - 入力は `offerRSS_gotoOffer` の申請フォーム画面だけで実行してください。マイページや申請状況確認画面では拒否します。

## 入力モード

- `一括入力`: 対象項目をまとめて入力します。
- `ゆっくり入力`: オプション内の補助機能です。対象項目を順番に入力し、入力中の項目をハイライトして右下に進捗を表示します。

## データファイル

- `../data/cases/demo_case_data.json`: 架空デモ案件の正規データ。
- `../data/generated/demo_application_data.json`: `demo_case_data.json` から生成した投入用JSON。
- `../data/form_definitions/rasens_offer_fields.json`: フォーム全項目台帳の正本。
- `../data/mappings/rasens_offer_mapping_v2.json`: canonical v2 データからフォーム入力行への変換ルール。backend が読み、拡張には同梱しません。

デモ投入JSONの再生成:

```bash
python ../../visa-eval/scripts/build_application_data.py \
  ../data/cases/demo_case_data.json \
  ../data/mappings/rasens_offer_mapping_v2.json \
  ../data/generated/demo_application_data.json
```

`build_application_data.js` と拡張同梱mappingは持たせません。`popup.js` は `/application-data` の取得と `fillable` / `warnings` 表示だけを担当し、`content.js` はDOM入力責務を担当します。

## 注意

この拡張およびQA作業では、申請の最終送信ボタンを絶対に押さないでください。入力後は確認・スクリーンショット・差分確認までに留め、送信が必要な場合は必ず人間が内容を最終確認してから手動で行ってください。

ファイル添付欄はChromeのセキュリティ制約で自動入力できません。顔写真と添付PDFは手動で選択してください。

`Could not establish connection. Receiving end does not exist.` が出る場合は、対象ページにcontent scriptが入っていない状態です。拡張をリロードした後は対象ページもリロードしてください。この拡張は送信失敗時に `content.js` を再注入して再試行しますが、Chrome内部ページや対象外URLでは実行できません。
