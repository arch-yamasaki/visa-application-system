# 09 取次者 autofill bug 修正計画

## 目的

Chrome拡張で RASENS の「取次者（オンラインシステム利用者）」欄が入力されない問題を切り分け、最小変更で直す。

これは Gemini 抽出の問題ではない。取次者は申請アカウントを持つ申請会社側の固定情報であり、申請人・勤務先・代理人とは別に扱う。

## 対象項目

RASENS 画面上では次の5項目を確認する。

| 項目 | 入力元 | 備考 |
|---|---|---|
| 取次者 氏名 | 固定設定 | 太田さん側の申請アカウント情報 |
| 取次者 郵便番号 | 固定設定 | 勤務先会社情報ではない |
| 取次者 住所 | 固定設定 | 勤務先会社情報ではない |
| 取次者 所属機関等 | 固定設定 | 申請会社名 |
| 取次者 電話番号 | 固定設定 | 申請会社電話番号 |

## 切り分け順

1. `/cases/{case_id}/application-data` の `rows` に取次者5項目が含まれるか確認する。
2. `rows` に含まれない場合は、backend の固定設定注入を確認する。
3. `rows` に含まれる場合は、Chrome拡張の DOM 探索、mapping、form definition を確認する。
4. 実 RASENS 画面では入力結果と missed 件数だけ確認し、最終送信はしない。

## 調査対象ファイル

| 領域 | ファイル | 確認内容 |
|---|---|---|
| backend | `visa-app/backend/application_data.py` | `settings.intermediary` または `INTERMEDIARY_*` から rows を作れているか |
| backend | `visa-app/backend/main.py` | `/cases/{case_id}/application-data` が取次者 rows を返すか |
| backend test | `visa-app/backend/tests/test_application_data.py` | 取次者 rows のテスト有無 |
| mapping | `rasens-autofill/data/mappings/rasens_offer_mapping_v2.json` | 取次者 canonical path と RASENS 項目の対応 |
| form definition | `rasens-autofill/data/form_definitions/rasens_offer_fields.json` | RASENS の field_id / field_name / label |
| extension | `rasens-autofill/extension/content.js` | 入力先探索と missed reason |
| extension | `rasens-autofill/extension/popup.js` | 読み込んだ rows の表示・実行導線 |

## 受け入れ条件

- `/application-data` に取次者5項目が含まれる。
- Chrome拡張で取次者5項目が入力対象に含まれる。
- 実 RASENS 画面で取次者5項目が入力される、または未検出の場合に項目名が console で特定できる。
- 代理人欄には勤務先会社情報、取次者欄には固定設定が入り、両者が混ざらない。

## QA

### API確認

```bash
curl -s "$VISA_APP_URL/cases/<case_id>/application-data" \
  | jq '.rows[] | select(.label | test("取次者"))'
```

確認すること:

- 5行あること
- `fill_value` が空でないこと
- 勤務先会社名やフジタ情報が取次者固定情報として混入していないこと

### Chrome DevTools MCP確認

1. RASENS画面を開く。
2. Chrome拡張で対象caseを選択し、visa-appから読み込む。
3. 一括入力を実行する。
4. DevTools console で missed reason を確認する。
5. 取次者欄が入力されたスクリーンショットを `qa/screenshots/` に保存する。実PIIを含むためgitには入れない。

## 実装方針

まず backend rows の有無で原因を分ける。

- rows がない: `application_data.py` の固定設定注入を直す。
- rows がある: `content.js` の入力先探索または mapping / form definition を直す。

余計な互換処理は増やさない。取次者は固定設定、代理人は勤務先会社情報という責務を保つ。

