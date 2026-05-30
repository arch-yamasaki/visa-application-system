# Chrome拡張連携の作業計画

## 目的

visa-app で抽出・編集した `case_data` を、Chrome拡張経由で RASENS フォームへ投入できるようにする。

Chrome拡張は、`case_data` や mapping を解釈しない。backend の `/cases/{case_id}/application-data` が生成した `rows` を受け取り、RASENS DOM に入力する薄い責務にする。

## 現状のデータフロー

```text
visa-app Firestore case
  -> backend /cases/{case_id}/application-data
  -> rasens-autofill/extension/api_client.js
  -> popup.js
  -> chrome.storage.local
  -> content.js
  -> RASENS form
```

## 主要ファイル

| 領域 | ファイル | 役割 |
| --- | --- | --- |
| backend | `visa-app/backend/application_data.py` | case_data + mapping + form_definitions から `rows` を生成 |
| backend | `visa-app/backend/main.py` | `/cases/{case_id}/application-data` API |
| backend test | `visa-app/backend/tests/test_application_data.py` | application-data の生成テスト |
| mapping | `rasens-autofill/data/mappings/rasens_offer_mapping_v2.json` | canonical path と RASENS 項目の対応 |
| form definition | `rasens-autofill/data/form_definitions/rasens_offer_fields.json` | RASENS フォーム項目台帳 |
| extension | `rasens-autofill/extension/api_client.js` | visa-app API 通信 |
| extension | `rasens-autofill/extension/popup.js` | case ID 入力、データ取得、保存、投入ボタン制御 |
| extension | `rasens-autofill/extension/content.js` | RASENS DOM への入力 |
| extension | `rasens-autofill/extension/popup.html` | 拡張ポップアップUI |
| QA | `rasens-autofill/QA_POLICY.md` | 最終送信禁止、PII取扱い |

## いま残っている問題

### 1. 実RASENS画面での field_id / field_name 適合率が未確定

`content.js` は `field_id`、`field_name`、ラベル近似で入力先を探す。

実画面では RASENS 側のDOM差分、select option 表記、radio / checkbox の値表記で missed が出る可能性がある。

### 2. QAの安全線を保つ必要がある

Chrome拡張QAでは、申請の最終送信を絶対に押さない。

実PIIを使う場合は、専用Chromeプロファイル、`chrome.storage.local` 削除、スクリーンショット管理が必要。

### 3. 取次者がRASENSに入力されない

`/application-data` では取次者欄を `settings.intermediary` または `INTERMEDIARY_*` 環境変数から注入する設計だが、実RASENS画面で取次者（オンラインシステム利用者）の5項目が入力されないバグが残っている。

確認する項目:

- 取次者 氏名
- 取次者 郵便番号
- 取次者 住所
- 取次者 所属機関等
- 取次者 電話番号

まず `/cases/{case_id}/application-data` の rows に上記5項目が含まれるかを確認し、含まれる場合は Chrome拡張の DOM 探索または field mapping 側を確認する。rows に含まれない場合は backend の固定設定注入を確認する。

## 今回対応済み

- backend の `workflow_state` 新規保存を `draft / extracting / extracted / failed` に寄せた。
- `/application-data` は `extracted / needs_review / ready_to_fill` を `fillable=true` として扱う。
- warning は `workflow_state is not fillable: ...` に変更し、`ready_to_fill` 固有表現を消した。
- Chrome拡張popupの表示を `未抽出 / 抽出中 / 抽出済み / 抽出失敗` に寄せた。
- `api_client.js` の case 一覧取得から `workflow_state=ready_to_fill` 固定を外した。
- Cloud Run コンテナへ `backend/data/form_definitions/rasens_offer_fields.json` を同梱した。
- Chrome拡張の既定API URLを Cloud Run にした。ローカル開発時だけ `http://localhost:8080` に上書きする。
- `application-data` で法人番号の有無、所属機関の主たる業種、資本金、年間売上高、従業員数、外国人職員数、技能実習生数を生成対象に追加した。
- `application-data` で上陸予定港、滞在予定期間、同伴者、過去入出国歴、過去COE申請歴、犯罪歴、契約形態をMVP既定値で補完する。
- `application-data` で最終学歴 23.1/23.2/23.3、過去COE申請歴 18.2/18.3、退去強制・出国命令 20.1/20.2/20.3 を生成対象に追加した。
- `application-data` で就労予定期間 5.1/5.2/5.3 を生成対象に追加し、空の場合は `定めあり Fixed` / `1` / `0` を初期値にする。
- `application-data` で代理人欄を勤務先会社情報から初期化する。取次者欄は `settings.intermediary` または `INTERMEDIARY_*` 環境変数から注入する。
- Chrome拡張のradio選択を各選択肢ラベル基準に変更し、`無 No` が同じ行の `有 Yes` に吸われる問題を修正した。
- Chrome拡張のselect探索で、同じnameに複数候補がある場合は表示中の要素を優先するようにした。

## 役割分担

### PdM

- MVPで拡張投入を許可する条件を決める。
- 推奨は `extracted / needs_review / ready_to_fill` を投入可能扱いにする。
- 「抽出済みだが人間確認前」という警告文を残すかを決める。

### Lead Engineer

- `/application-data` の `fillable` 判定を整理する。
- backend と extension の状態正規化を揃える。
- mapping v2 と form definition を正本として扱い、拡張側に変換ロジックを増やさない。

### Engineer

- `application_data.py` の `fillable` 判定を更新する。
- `api_client.js` の一覧取得を `ready_to_fill` 固定から外す。
- `popup.js` の状態表示を4状態へ更新する。
- 必要なら `content.js` の missed reason を集計しやすくする。

### QA

- `/application-data` のレスポンスを case ID 指定で確認する。
- Chrome拡張で `visa-appから読込`、`入力対象を確認`、`一括入力`、`ゆっくり入力` を確認する。
- RASENS実画面では最終送信を押さず、入力結果と missed 件数だけ確認する。

### Documentation

- 状態管理の移行方針を `003_workflow_state_simplification` に反映する。
- Chrome拡張QA手順と禁止事項をこのディレクトリまたは `rasens-autofill/QA_POLICY.md` に追記する。

## 最小作業計画

### Step 1. backend API互換を入れる

対応済み。`application_data.py` の投入可能状態を広げた。

```py
fillable = workflow_state in {"extracted", "needs_review", "ready_to_fill"}
```

warning 文言も `workflow_state is not fillable` のように状態名に依存しない表現へ変える。

テスト:

- `extracted` は `fillable=true`
- `needs_review` は移行互換で `fillable=true`
- `ready_to_fill` は移行互換で `fillable=true`
- `draft / extracting / failed` は `fillable=false`

### Step 2. Chrome拡張の状態表示を4状態にする

対応済み。`popup.js` に frontend と同じ表示正規化を入れた。

表示:

- `draft / uploading` -> 未抽出
- `extracting` -> 抽出中
- `needs_review / ready_to_fill / extracted` -> 抽出済み
- `extraction_failed / launch_failed / failed` -> 抽出失敗

### Step 3. case 一覧取得を見直す

対応済み。拡張の主導線は `/cases` の案件一覧選択にし、一覧取得から `ready_to_fill` 固定を外した。`case_id` 手入力欄は、一覧取得失敗時や一覧外案件のfallbackとして残す。

### Step 4. 実画面QA

1. visa-app local backend を起動する。
2. Chrome拡張に `http://localhost:8080` を設定する。
3. 案件一覧から対象caseを選び、`/application-data` を取得する。必要なら case ID 手入力fallbackも確認する。
4. `入力対象を確認` で rows 件数と skipped / manual_required を確認する。
5. RASENS入力画面で `ゆっくり入力` を実行する。
6. filled / missed の件数と missed reason を確認する。
7. 最終送信は押さない。

## 受け入れ条件

- `extracted` 相当のケースで `/application-data` が `fillable=true` を返す。
- Chrome拡張で案件一覧からcaseを選択して取得できる。
- Chrome拡張で case ID 手入力fallback取得ができる。
- 取次者5項目が `/application-data` に含まれ、RASENS画面で入力される。
- 拡張ポップアップに `要レビュー` / `入力準備完了` が表示されない。
- `rows` が `chrome.storage.local` に保存され、投入ボタンが有効になる。
- RASENS画面で preview / fill / progressive fill が動く。
- missed が出た場合、どの row がなぜ入らなかったか確認できる。
- 最終送信を押さないQA手順が明記されている。

## 注意点

- Chrome拡張には mapping 解釈を戻さない。
- 実案件データを `extension/application_data.json` に保存しない。
- `chrome.storage.local` に前回案件の rows が残るため、実データQA後は削除する。
- RASENSのDOMが変わる可能性があるため、`field_id` / `field_name` / label fallback の順で確認する。
- select option の表記ゆれは mapping / form definition 側で吸収する。content script に個別業務ルールを増やさない。
