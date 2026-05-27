# 案件選択・レビュー順序改善の作業計画

## 目的

`case_id` コピペに依存せず、visa-app の案件一覧、Chrome拡張の案件選択、レビュー画面の確認順を実務で使いやすい形に揃える。

今回の中心は次の2つ。

- 案件を人が選べるようにするための `CaseSummary`
- RASENS申込フォーム順で確認できるレビューUI

## 現状の課題

### 1. レビューUIの順番がRASENS申込フォームと違う

現在のレビュー画面は、`case_data` を flatten した順番と `fieldPaths.ts` のセクション定義に依存している。

そのため、データ構造としては自然でも、RASENS申込フォームを見ながら確認する順番とはズレる。

例:

```text
現在の見え方:
  身分事項 applicant.*
  入国計画 entry_plan.*
  申請人に関する情報 education.*
  所属機関 employer.*

RASENSに近い見え方:
  主たる活動内容
  国籍・地域
  生年月日
  氏名
  ...
  旅券番号
  入国目的
  入国予定年月日
  上陸予定港
  滞在予定期間
```

### 2. 案件一覧が `case_id` 中心で識別しづらい

現在の `/cases` summary は主に次の情報だけを返す。

```ts
type CaseSummary = {
  case_id: string
  workflow_state: string
  created_at: string
  applicant_name_preview?: string
}
```

実務では `case_498ec046934a` だけでは、どの申請人・どの所属機関の案件か判断しづらい。

### 3. Chrome拡張で `case_id` を手入力している

現在の Chrome拡張 popup は `case_id` を入力して `/cases/{case_id}/application-data` を読む。

内部処理として `case_id` を使うのは正しいが、ユーザー操作としては案件名・申請人名・所属機関名から選べる方がよい。

## 対象範囲

- backend `/cases` の summary 拡張
- frontend 案件一覧の表示改善
- Chrome拡張 popup の案件選択
- レビューUIの RASENS順表示
- 関連docsとQA観点の整理

## 非対象

- `case_data` の大規模schema変更
- Chrome拡張側で mapping / transform を解釈する設計への戻し
- RASENS最終送信の自動化
- 案件名編集UI
- API認証の本実装

API認証は本番前に必要だが、この作業ではリスクとして明記するだけにする。

## CaseSummary設計

### CaseSummaryは何から作るか

`CaseSummary` は新しい保存データではなく、Firestore の `cases/{case_id}` document から `/cases` API が返す表示用DTOとして作る。

使う元データは次の通り。

```text
Firestore top-level:
  case_id
  workflow_state
  created_at
  updated_at
  case_title          # 将来、ユーザー編集可能な案件名を入れる場合のみ

case_data:
  applicant.name_roman
  applicant.name_kanji
  employer.name
  case.target_status
  case.application_type
```

初期MVPでは `case_title` は保存しない。`_case_summary()` で毎回 `case_data` から表示名を生成する。

理由:

- 申請人名や所属機関名の正本は `case_data` にある
- summaryとして別保存すると、レビュー画面で値を直した時にズレる
- 一覧とChrome拡張に必要なのは保存構造ではなく、選択しやすい表示情報
- 将来、手入力の案件名が必要になった時だけ top-level `case_title` を足せばよい

### 推奨する返却型

```ts
type CaseSummary = {
  case_id: string
  display_name: string
  applicant_name?: string
  employer_name?: string
  target_status?: string
  application_type?: string
  workflow_state: string
  created_at: string
  updated_at?: string
}
```

### `display_name` の生成ルール

```text
display_name =
  case_title
  or applicant_name + " / " + employer_name
  or applicant_name
  or employer_name
  or case_id
```

例:

```text
AMIT TAMANG / 株式会社フジタ
NGUYEN VAN A / デモテクノロジー株式会社
株式会社フジタ
case_498ec046934a
```

### 保存するものと保存しないもの

保存する:

- `case_id`
- `workflow_state`
- `created_at`
- `updated_at`
- 将来の `case_title`

保存しない:

- `display_name`
- `applicant_name`
- `employer_name`
- `target_status`
- `application_type`

保存しない項目は、`case_data` から都度生成する。

## API設計

短期では既存の `GET /cases` を拡張する。

```http
GET /cases?limit=20
```

将来の追加候補:

```http
GET /cases?limit=50&query=amit&workflow_state=extracted&fillable_only=true
```

初期実装では `limit` と既存の `workflow_state` だけでよい。検索は案件数が増えてからでよい。

レスポンス例:

```json
[
  {
    "case_id": "case_498ec046934a",
    "display_name": "AMIT TAMANG / 株式会社フジタ",
    "applicant_name": "AMIT TAMANG",
    "employer_name": "株式会社フジタ",
    "target_status": "engineer_humanities_international",
    "application_type": "certificate_of_eligibility",
    "workflow_state": "extracted",
    "created_at": "2026-05-26T00:00:00+00:00",
    "updated_at": "2026-05-26T00:30:00+00:00"
  }
]
```

## visa-app一覧UI

一覧では `case_id` を主役にしない。

表示方針:

```text
AMIT TAMANG / 株式会社フジタ
申請人: AMIT TAMANG
所属機関: 株式会社フジタ
在留資格: 技術・人文知識・国際業務
状態: 抽出済み
ID: case_498ec046934a
```

`case_id` コピー機能は残す。通常操作では見出しにしないが、不具合調査やサポートでは必要になる。

## Chrome拡張案件選択

Chrome拡張はすでに `api_client.js` に `listCases()` を持っている。これを popup で使う。

責務は次のまま維持する。

```text
/cases
  -> 案件候補を表示するための summary を取得する

/cases/{case_id}/application-data
  -> 選択済みcaseの入力rowsを取得する
```

popupのMVP UI:

```text
visa-app から読込

[案件を選択]
  AMIT TAMANG / 株式会社フジタ / 抽出済み
  NGUYEN VAN A / デモ会社 / 抽出済み

[選択した案件を読込]

詳細:
  ID: case_498ec046934a
```

内部値は必ず `case_id` にする。表示名が同じ案件があっても、取得先は `case_id` で一意に決まる。

case_id手入力欄は、初期MVPでは詳細またはfallbackとして残してよい。通常導線は案件選択にする。

## レビューUI RASENS順化

レビューUIの並び順は、`case_data` の構造順ではなく `rasens_offer_mapping_v2.json` の `form_order` を使う。

フォーム順と繰り返し項目の詳細は [form_order_detail_design.md](form_order_detail_design.md) に置く。

正本の考え方:

| 種類 | 役割 |
| --- | --- |
| `rasens_offer_fields.json` | RASENSフォーム全体の物理順 |
| `rasens_offer_mapping_v2.json` | MVPで入力・レビュー対象にする canonical path と RASENS項目の対応 |
| `review_field_catalog.md` | 人間向けの設計台帳 |

短期実装では、`rasens_offer_mapping_v2.json` の `value_path` と `form_order` から `canonical_path -> order` を作り、レビューUIを並べる。

注意:

- `display_no` は人間向けの参考番号であり、IDとして扱わない
- RASENS側の番号は重複や飛びがあるので、技術的な一意キーにしない
- 技術キーは `canonical_path`
- 並び順は `form_order`

mappingにないがレビューしたい項目は、近いセクション末尾または「その他」に置く。

`supporting_documents` や `assessments` は RASENS入力値ではないため、通常の申込フォーム順レビューとは別扱いにする。

### 親族・職歴の繰り返し項目

次の2ブロックはフォーム順に追加する。

| 位置 | RASENS参考番号 | 表示 | canonical path | UI |
| --- | --- | --- | --- | --- |
| 身分事項 20.3 の直後 | 21.1 | 在日親族及び同居者 有無 | `applicant.family.has_japan_relatives_or_cohabitants` | 通常行 |
| 身分事項 21.1 の直後 | 21.2-21.8 | 在日親族及び同居者 1〜3件 | `applicant.family.japan_relatives_or_cohabitants[0..2].*` | 折りたたみ繰り返しUI |
| 申請人に関する情報等 25.2 の直後 | - | 職歴の有無 | `applicant.has_employment_history` | 通常行 |
| 職歴の有無の直後 | 国・地域名 + 26.1-26.6 | 職歴 1〜3件 | `applicant.employment_history[0..2].*` | 折りたたみ繰り返しUI |

親族・職歴はいずれも最大3件まで扱う。RASENSフォーム側にはそれ以上の枠があるが、MVPでは4件以上を要手入力/要確認扱いにする。

Firestoreには空の3枠を常時保存しない。入力がある行だけ配列に保存し、UI側だけ最大3枠を表示できるようにする。

既存の `flattenCaseData()` による通常行表示と繰り返し専用UIが二重表示になる場合、配列配下の通常行は削除する。

## 作業フェーズ

親族・職歴の繰り返し項目だけは、詳細設計の [作業計画レビュー](form_order_detail_design.md#作業計画レビュー) を優先し、backend schema / prompt、canonical docs、frontend UI、mapping / application-data、QAの順で進める。

### Phase 1. CaseSummaryを強化する

対象:

- `visa-app/backend/main.py`
- `visa-app/frontend/src/types/caseData.ts`
- `visa-app/frontend/src/api/mockData.ts`

作業:

- `_case_summary()` に `display_name`, `applicant_name`, `employer_name`, `target_status`, `application_type`, `updated_at` を追加する
- `display_name` は保存せず、`case_data` から生成する
- 既存の `applicant_name_preview` は互換のため一時的に残すか、frontend更新と同時に置き換える

QA:

- 申請人名と所属機関名がある場合は `申請人 / 所属機関` になる
- 申請人名だけの場合は申請人名になる
- どちらもない場合は `case_id` になる
- 既存 `/cases/{case_id}` と `/cases/{case_id}/application-data` は変わらない

### Phase 2. visa-app案件一覧を改善する

対象:

- `visa-app/frontend/src/pages/CaseListPage.tsx`
- `visa-app/frontend/src/components/common/CopyableCaseId.tsx`

作業:

- 主表示を `display_name` にする
- 申請人、所属機関、在留資格、状態を見えるようにする
- `case_id` コピーは補助情報として残す

QA:

- case_idだけの案件でも一覧が壊れない
- 抽出済み案件は申請人・所属機関が見える
- クリック時の遷移先は既存通り `workflow_state` で分岐する

### Phase 3. Chrome拡張で案件を選択できるようにする

対象:

- `rasens-autofill/extension/api_client.js`
- `rasens-autofill/extension/popup.html`
- `rasens-autofill/extension/popup.js`
- `rasens-autofill/extension/popup.css`
- `rasens-autofill/extension/README.md`

作業:

- popup起動時に `listCases()` を呼ぶ
- selectに `display_name` と状態を表示する
- 選択された `case_id` で `getApplicationData(case_id)` を呼ぶ
- 読込後の `visaDataSource` に `display_name` を入れる
- 読込失敗時は既存rowsをclearする

QA:

- case_idを手入力せずに rows を取得できる
- 選択した案件と取得した rows の `case_id` が一致する
- `/cases` 取得失敗時に前回データが残らない
- Cloud Run URLでCORSエラーが出ない

### Phase 4. レビューUIをRASENS順にする

状態: 一部完了。親族・職歴の最大3件折りたたみUI、通常行との二重表示削除、職歴有無のセクション配置は実装済み。

対象:

- `visa-app/frontend/src/components/review/FieldPanel.tsx`
- `visa-app/frontend/src/lib/fieldPaths.ts`
- 新規候補: `visa-app/frontend/src/lib/reviewFieldOrder.ts`

作業:

- `canonical_path -> form_order` のorder mapを作る
- `FieldPanel` の項目sortにorder mapを使う
- mappingにない項目は既存セクション順の末尾へ送る
- RASENSの `display_no` は表示補助にとどめる
- `21.1〜21.8` 在日親族及び同居者を身分事項に追加する
- 職歴の有無、国・地域名、`26.1〜26.6` を申請人に関する情報等に追加する
- 親族・職歴は最大3件の折りたたみ繰り返しUIにする
- `applicant.family.japan_relatives_or_cohabitants.*` と `applicant.employment_history.*` の通常行二重表示を削除する

QA:

- `入国目的`, `入国予定年月日`, `上陸予定港`, `滞在予定期間` がRASENS順に近い位置に出る
- `契約の形態` と所属機関情報が申込フォーム順に近い順で出る
- `21.1` が `20.3` の直後に出る
- 在日親族・同居者を最大3件まで追加・編集できる
- 職歴を最大3件まで追加・編集できる
- 配列項目が通常行と専用UIで二重表示されない
- 証跡表示、編集、保存は既存通り動く

### Phase 5. Gemini schema / prompt を更新する

状態: 完了。親族・職歴のschema追加、最大3件・空配列・boolean false のprompt指示を反映済み。

対象:

- `visa-app/backend/extractors/schema.py`
- `visa-app/backend/extractors/prompt_template.py`
- `visa-app/frontend/src/types/caseData.ts`

作業:

- `applicant.family.japan_relatives_or_cohabitants[]` の詳細項目をschema化する
- `applicant.has_employment_history` を追加する
- `applicant.employment_history[]` に `country_region`, `start_month_unknown`, `end_month_unknown`, `company_name_local` を揃える
- prompt に「最大3件、なければ空配列、booleanはfalse」を明記する

QA:

- 書類に情報がない場合、親族・職歴の有無は `false`、明細配列は空になる
- 書類に情報がある場合、最大3件まで抽出される
- 空欄の明細行をGeminiが生成しない

### Phase 6. mapping / application-data を更新する

状態: 完了。親族・職歴の最大3件mapping、boolean gating、`month_unknown` transform、backend/extension mapping同期を反映済み。

対象:

- `visa-app/backend/data/mappings/rasens_offer_mapping_v2.json`
- `rasens-autofill/data/mappings/rasens_offer_mapping_v2.json`
- `visa-app/backend/application_data.py`
- `visa-app/backend/tests/test_application_data.py`

作業:

- 親族・職歴の最大3件分の固定index mappingを追加する
- 親族明細は `applicant.family.has_japan_relatives_or_cohabitants == true` の時だけ出す
- 職歴明細は `applicant.has_employment_history == true` の時だけ出す
- 空欄値は rows に出さない
- backend と extension の mapping 同期を維持する

QA:

- `/application-data` に親族・職歴の値が必要な時だけ出る
- 空欄行がrowsに混ざらない
- Chrome拡張側に変換ロジックを増やさない

### Phase 7. docs更新と回帰確認

対象:

- `visa-app/docs/002_review_field_order/README.md`
- `visa-app/docs/002_review_field_order/canonical_case_data_v2.md`
- `visa-app/docs/002_review_field_order/review_field_catalog.md`
- `visa-app/docs/004_chrome_extension_integration/README.md`
- `visa-app/docs/README.md`

作業:

- RASENS順の正本を `form_order` と明記する
- Chrome拡張は `/cases` で選択、`/application-data` でrows取得と明記する
- `case_id` 手入力中心の説明を案件選択中心に更新する
- 親族・職歴は最大3件の繰り返しUIとして明記する

QA:

- backend test
- frontend build
- extension `node --check`
- Chrome拡張 popup 手動確認
- RASENS画面では最終送信しない

## 受け入れ条件

- `/cases` が `display_name`, `applicant_name`, `employer_name`, `workflow_state`, `created_at`, `updated_at` を返す
- 申請人名や所属機関名が空でも、最後は `case_id` で表示できる
- visa-app案件一覧で `case_id` だけでなく、申請人名・所属機関名・状態が見える
- Chrome拡張で `case_id` を手入力せず、案件候補から選んで `/application-data` を取得できる
- Chrome拡張の内部処理は引き続き `case_id` で取得する
- レビューUIの主要項目が `form_order` ベースでRASENS順に並ぶ
- `21.1〜21.8` 在日親族及び同居者が最大3件まで編集できる
- 職歴の有無、国・地域名、`26.1〜26.6` が最大3件まで編集できる
- 配列項目の通常行と繰り返し専用UIが二重表示されない
- RASENSの画面番号はID扱いしない
- mappingやtransformロジックをChrome拡張側に戻さない

## リスクと意思決定

### `/cases` に申請人名・会社名を返すリスク

Cloud Run が unauthenticated の間は、`/cases` に個人名・会社名を返すと外部から見える可能性がある。

MVP検証では利便性を優先して進める。本番前にAPI認証、IAP、または返却情報の制限を検討する。

### `display_name` を保存しないことによる計算コスト

今の件数では問題にならない。Firestore全件streamとPython sortの方が先にボトルネックになる。

件数が増えたら、`case_search_text` や `case_title` のtop-level保存を検討する。

### レビューUIをRASENS順にするとデータ構造順ではなくなる

`applicant.*` や `entry_plan.*` が混ざって見えるため、開発者目線では追いにくくなる。

ただし実務上はRASENS画面と照合するため、レビュー画面では申込フォーム順を優先する。

## 関連ファイル

| 領域 | ファイル | 役割 |
| --- | --- | --- |
| backend | `visa-app/backend/main.py` | `_case_summary()` と `/cases` |
| frontend | `visa-app/frontend/src/types/caseData.ts` | `CaseSummary` 型 |
| frontend | `visa-app/frontend/src/pages/CaseListPage.tsx` | 案件一覧 |
| frontend | `visa-app/frontend/src/components/review/FieldPanel.tsx` | レビュー項目表示 |
| frontend | `visa-app/frontend/src/lib/fieldPaths.ts` | ラベル、セクション、入力型 |
| docs | `visa-app/docs/005_case_navigation_and_review_order/form_order_detail_design.md` | RASENSフォーム順、親族・職歴の繰り返しUI、schema方針 |
| mapping | `visa-app/backend/data/mappings/rasens_offer_mapping_v2.json` | canonical path と RASENS順 |
| form definition | `visa-app/backend/data/form_definitions/rasens_offer_fields.json` | RASENSフォーム全体の物理順 |
| extension | `rasens-autofill/extension/api_client.js` | `/cases` と `/application-data` 通信 |
| extension | `rasens-autofill/extension/popup.html` | popup UI |
| extension | `rasens-autofill/extension/popup.js` | 案件選択、rows保存、投入操作 |
