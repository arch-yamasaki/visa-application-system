# レビューUI フォーム順詳細設計

## 目的

レビュー画面を `case_data` の構造順ではなく、RASENS申込フォームの確認順に寄せる。

この文書では、特に次の追加ブロックを含めた表示順、canonical path、Gemini schema、UI方針を定義する。

- 21.1〜21.8 在日親族及び同居者
- 職歴の有無
- 国・地域名 + 26.1〜26.6 職歴

## 正本の考え方

| 種類 | 役割 |
|---|---|
| `rasens_offer_fields.json` | RASENSフォーム全体の物理順。フォームに存在する項目の確認に使う |
| `rasens_offer_mapping_v2.json` | MVPでレビュー・自動入力する項目と canonical path の対応 |
| `canonical_case_data_v2.md` | Firestore `case_data` の意味上の正本 |
| この文書 | レビューUIでどう並べ、繰り返し項目をどう表示するかの詳細設計 |

RASENSの画面番号は、人間がフォームと照合するための参考番号であり、IDとして使わない。

技術的な一意キーは `canonical path`、並び順は `form_order` を使う。`form_order` が重複する場合は mapping JSON 内の出現順を副順にする。

## セクション順

| UI順 | RASENS範囲 | RASENS区分 | 扱い |
|---:|---|---|---|
| 1 | 1 | 申請概要 | 主たる活動内容 |
| 2 | 2-58 | 身分事項 | 申請人基本情報、入国計画、出入国歴、在日親族及び同居者 |
| 3 | 80-118 | 申請人に関する情報等 | 学歴、資格、職歴 |
| 4 | 159-164 | 代理人 | 代理人情報 |
| 5 | 167-171 | 取次者 | 固定値 |
| 6 | 174-210 | 所属機関に関する情報等 | 契約形態、所属機関、雇用条件、活動内容 |

既存の `入国計画`、`所属機関`、`雇用・活動内容` というデータ構造由来の区切りは、レビューUI上ではRASENS上の区分に寄せる。

## 追加ブロック1: 在日親族及び同居者

### 表示位置

`20.3 直近の送還年月日` の直後、身分事項内に表示する。

| UI順 | RASENS参考番号 | 表示項目 | canonical path | 入力方針 | 備考 |
|---:|---|---|---|---|---|
| 37 | 21.1 | 在日親族及び同居者 有無 | `applicant.family.has_japan_relatives_or_cohabitants` | Gemini抽出+人確認 | デフォルトは `false` |
| 38 | 21.2 | 在日親族・同居者1 続柄 | `applicant.family.japan_relatives_or_cohabitants.0.relationship` | 任意 | 有の場合のみ表示候補 |
| 39 | 21.3 | 在日親族・同居者1 氏名 | `applicant.family.japan_relatives_or_cohabitants.0.name` | 任意 |  |
| 40 | 21.4 | 在日親族・同居者1 生年月日 | `applicant.family.japan_relatives_or_cohabitants.0.birth_date` | 任意 | 日付精度の扱いは要実装設計 |
| 41 | 21.5 | 在日親族・同居者1 国籍・地域 | `applicant.family.japan_relatives_or_cohabitants.0.nationality_region` | 任意 |  |
| 42 | 21.6 | 在日親族・同居者1 同居予定の有無 | `applicant.family.japan_relatives_or_cohabitants.0.will_cohabit` | 任意 | boolean/select |
| 43 | 21.7 | 在日親族・同居者1 勤務先・通学先 | `applicant.family.japan_relatives_or_cohabitants.0.workplace_or_school_name` | 任意 |  |
| 44 | 21.8 | 在日親族・同居者1 在留カード番号等 | `applicant.family.japan_relatives_or_cohabitants.0.residence_card_or_certificate_number` | 任意 |  |
| 45-58 | 21.2-21.8 | 在日親族・同居者2-3 | `applicant.family.japan_relatives_or_cohabitants.1.*` / `.2.*` | 任意 | MVPは最大3件 |

### データ形

Firestoreには空の3枠を常時保存しない。入力がある行だけ配列に保存する。

```json
{
  "applicant": {
    "family": {
      "has_japan_relatives_or_cohabitants": false,
      "japan_relatives_or_cohabitants": [
        {
          "relationship": "",
          "name": "",
          "birth_date": "",
          "nationality_region": "",
          "will_cohabit": "",
          "workplace_or_school_name": "",
          "residence_card_or_certificate_number": ""
        }
      ]
    }
  }
}
```

### UI方針

通常の `FieldRow` を7行ずつ並べるのではなく、繰り返し入力UIにする。

```text
21.1 在日親族及び同居者 有無  [無 / 有]

▶ 在日親族・同居者 詳細 0/3件
  [+ 追加]
```

ルール:

- 最大3件
- 初期状態は閉じる
- `有` の場合、または既存データがある場合は詳細を開きやすくする
- 空欄のまま保存できる
- 空欄行は application-data rows に出さない
- RASENS側は6件分あるが、MVPでは3件まで。4件以上は要手入力・要確認扱い

## 追加ブロック2: 職歴

### 表示位置

`25.2 情報処理資格名又は試験名` の直後、申請人に関する情報等に表示する。

| UI順 | RASENS参考番号 | 表示項目 | canonical path | 入力方針 | 備考 |
|---:|---|---|---|---|---|
| 91 | 職歴の有無 | 職歴の有無 | `applicant.has_employment_history` | Gemini抽出+人確認 | デフォルトは `false` |
| 92 | 国・地域名 | 職歴1 国・地域名 | `applicant.employment_history.0.country_region` | 任意 | RASENS上の職歴行の先頭 |
| 93 | 26.1 | 職歴1 入社月不詳 | `applicant.employment_history.0.start_month_unknown` | 任意 | boolean/select |
| 94 | 26.2 | 職歴1 入社年月 | `applicant.employment_history.0.start_date` | 任意 | 年月 |
| 95 | 26.3 | 職歴1 退社月不詳 | `applicant.employment_history.0.end_month_unknown` | 任意 | boolean/select |
| 96 | 26.4 | 職歴1 退社年月 | `applicant.employment_history.0.end_date` | 任意 | 年月 |
| 97 | 26.5 | 職歴1 勤務先名称 英字 | `applicant.employment_history.0.company_name_en` | 任意 |  |
| 98 | 26.6 | 職歴1 勤務先名称 漢字 | `applicant.employment_history.0.company_name_local` | 任意 |  |
| 99-118 | 国・地域名 + 26.1-26.6 | 職歴2-3 | `applicant.employment_history.1.*` / `.2.*` | 任意 | MVPは最大3件 |

### データ形

`has_employment_history` は配列の外に置く。`employment_history` は配列のまま保つ。

```json
{
  "applicant": {
    "has_employment_history": false,
    "employment_history": [
      {
        "country_region": "",
        "start_month_unknown": false,
        "start_date": "",
        "end_month_unknown": false,
        "end_date": "",
        "company_name_en": "",
        "company_name_local": ""
      }
    ]
  }
}
```

理由:

- `applicant.employment_history[]` は既存方針と合う
- 有無フラグを配列内に入れると、職歴0件時に表現しづらい
- 配列を object に変えるより影響範囲が小さい

### UI方針

```text
職歴の有無  [無 / 有]

▶ 職歴 詳細 0/3件
  [+ 追加]
```

ルール:

- 最大3件
- 初期状態は閉じる
- `有` の場合、または既存データがある場合は詳細を開きやすくする
- 空欄のまま保存できる
- 空欄行は application-data rows に出さない
- 4件以上はMVPでは要手入力・要確認扱い

## 二重表示を避ける方針

現状のレビューUIは `case_data` を flatten して通常の `FieldRow` として表示する。

そのまま配列UIを追加すると、次のように二重表示になる。

```text
職歴 詳細カード
applicant.employment_history.0.country_region の通常行
applicant.employment_history.0.start_date の通常行
...
```

これを避けるため、繰り返しUIで扱う配下は通常flatten表示から除外する。

除外対象:

```text
applicant.family.japan_relatives_or_cohabitants.*
applicant.employment_history.*
```

代わりに、RASENS順の位置へ専用の繰り返しブロックを差し込む。

削除方針:

- 二重表示になる通常行は削除してよい
- 値そのものは削除しない
- 編集・保存は既存の `onFieldUpdate(path, value)` を使い回す
- 行削除は初期実装では物理削除ではなく、その件の値を空にする方式でよい

## Gemini schema 方針

現在の `schema.py` は次の状態。

- `applicant.family.has_japan_relatives_or_cohabitants` はある
- `applicant.family.japan_relatives_or_cohabitants[]` の詳細schemaはない
- `applicant.employment_history[]` の詳細schemaはfallback/doc上にはあるが、scope schemaとしては弱い
- `applicant.has_employment_history` はまだ明示されていない

追加方針:

| 項目 | schema扱い |
|---|---|
| `applicant.family.has_japan_relatives_or_cohabitants` | S1に残す。なければ `false` |
| `applicant.family.japan_relatives_or_cohabitants[]` | S1に最大3件の配列として追加 |
| `applicant.has_employment_history` | S3に boolean として追加 |
| `applicant.employment_history[]` | S3に最大3件の配列として追加 |

Geminiへの指示:

- 書類に明記があれば最大3件まで抽出する
- なければ有無フラグは `false`
- なければ明細配列は `[]`
- 空の明細行を無理に作らせない
- 不明な値は空文字にする
- 4件以上ある場合は先頭3件まで抽出し、review findingsに「4件以上あり」を出す

Gemini APIのschema制約を考慮し、S1/S3 scopeに分けて追加する。全体schemaにだけ巨大な配列を足して、states数を増やしすぎない。

## application-data / Chrome拡張方針

backend generator は固定index pathとして rows を作れる。

例:

```text
applicant.family.japan_relatives_or_cohabitants.0.relationship
applicant.family.japan_relatives_or_cohabitants.1.relationship
applicant.family.japan_relatives_or_cohabitants.2.relationship

applicant.employment_history.0.company_name_en
applicant.employment_history.1.company_name_en
applicant.employment_history.2.company_name_en
```

方針:

- mappingには最大3件分だけ追加する
- `visible_when` は有無フラグを見る
- 空欄値は rows 生成時にスキップする
- transform / visible_when はbackendに閉じる
- Chrome拡張は引き続き rows をDOMに入力するだけにする

## 受け入れ条件

- 21.1 が身分事項のRASENS順に表示される
- 在日親族・同居者の詳細を最大3件まで追加・編集できる
- 職歴の有無が申請人に関する情報等のRASENS順に表示される
- 職歴を最大3件まで追加・編集できる
- 初期状態では詳細が閉じていて、画面が重くならない
- 空欄の詳細行があっても保存できる
- 配列配下が通常 `FieldRow` と二重表示されない
- application-data では空欄行が出ない
- Chrome拡張に mapping / transform ロジックを戻さない
- Gemini schemaは空配列許容、最大3件抽出、なければ `false` を明示する

## 実装順

1. docs更新
   - `canonical_case_data_v2.md`
   - `review_field_catalog.md`
   - この文書
2. Gemini schema / prompt 更新
   - 親族明細配列
   - 職歴有無
   - 職歴配列
   - 最大3件、空配列、デフォルトfalse
3. review UI 更新
   - RASENS順order map
   - `RepeatedFieldGroup`
   - flatten除外
4. application-data mapping 更新
   - 21.1〜21.8 最大3件
   - 職歴の有無、国・地域名、26.1〜26.6 最大3件
5. QA
   - 空欄保存
   - 有/無切替
   - 二重表示なし
   - rows生成
   - Chrome拡張投入

## 作業計画レビュー

親族・職歴の繰り返し項目は、抽出、保存、レビューUI、Chrome拡張投入が連動する。実装時は次の順に確認しながら進める。

### 1. backend schema / prompt

対象:

- `visa-app/backend/extractors/schema.py`
- `visa-app/backend/extractors/prompt_template.py`

更新内容:

- `applicant.family.japan_relatives_or_cohabitants[]` をGemini schemaに追加する。
- `applicant.has_employment_history` を追加する。
- `applicant.employment_history[]` に職歴明細を追加する。
- promptに「最大3件、情報がなければbooleanはfalse、明細配列は `[]`」と明記する。
- 空欄の明細行をGeminiに作らせない。

影響範囲:

- schemaのstate数が増える。配列は最大3件前提にして、余計なネストや詳細source配列は増やさない。
- 親族は `identity` scope、職歴は `education` scopeまたは職歴用scopeの追加候補になる。
- 出力後の正規化処理が配列pathを扱えるか確認する。

### 2. canonical docs

対象:

- `visa-app/docs/002_review_field_order/canonical_case_data_v2.md`
- `visa-app/docs/002_review_field_order/review_field_catalog.md`
- `visa-app/docs/005_case_navigation_and_review_order/form_order_detail_design.md`

更新内容:

- 親族明細のcanonical pathを明記する。
- 職歴の有無と職歴明細のcanonical pathを明記する。
- RASENSフォーム順では `21.1-21.8` を身分事項、職歴を申請人に関する情報等に置く。
- RASENS参考番号はIDではないことを維持する。
- 最大3件はUI制約であり、Firestore schema上の配列そのものは3件固定ではないと明記する。

影響範囲:

- 旧pathの `family.*`, `family_in_japan`, top-level `employment_history[]` を復活させない。
- `applicant.employment_history[]` は既存方針を維持する。
- `has_employment_history` は `applicant` 直下に置き、配列object化しない。

### 3. frontend UI

対象:

- `visa-app/frontend/src/components/review/FieldPanel.tsx`
- `visa-app/frontend/src/lib/fieldPaths.ts`
- 新規候補: `visa-app/frontend/src/components/review/RepeatedFieldGroup.tsx`
- 新規候補: `visa-app/frontend/src/lib/reviewFieldOrder.ts`

更新内容:

- `21.1` と `applicant.has_employment_history` は通常の `FieldRow` として表示する。
- 親族明細と職歴明細は折りたたみの繰り返しUIで表示する。
- 最大3件まで追加・編集できるようにする。
- 初期状態では詳細を閉じる。
- 値がある明細は見つけやすい表示にする。

二重表示削除:

`FieldPanel` は `flattenCaseData()` で配列配下も通常行に展開する。繰り返しUIを入れる時は、次の配下を通常 `FieldRow` から除外する。

```text
applicant.family.japan_relatives_or_cohabitants.*
applicant.employment_history.*
```

残す通常行:

```text
applicant.family.has_japan_relatives_or_cohabitants
applicant.has_employment_history
```

影響範囲:

- 証跡表示は各明細pathごとに維持する。
- `onFieldUpdate(path, value)` は既存のdot path更新を使い回す。
- 削除操作は初期MVPでは物理削除ではなく、その明細の値を空にする方が影響が小さい。

### 4. mapping / application-data

対象:

- `visa-app/backend/data/mappings/rasens_offer_mapping_v2.json`
- `rasens-autofill/data/mappings/rasens_offer_mapping_v2.json`
- `visa-app/backend/application_data.py`
- `visa-app/backend/tests/test_application_data.py`

更新内容:

- 親族明細3件分の固定index mappingを追加する。
- 職歴明細3件分の固定index mappingを追加する。
- 親族明細は `applicant.family.has_japan_relatives_or_cohabitants == true` の時だけrowsにする。
- 職歴明細は `applicant.has_employment_history == true` の時だけrowsにする。
- 空欄値はrowsにしない。
- backend mapping と extension mapping を同期する。

影響範囲:

- Chrome拡張側にmapping/transform解釈を戻さない。
- `application-data` rowsの生成責務はbackendに残す。
- 月不詳や年月入力はRASENS form definitionと突合して、必要ならtransformを追加する。

### 5. QA

確認内容:

- Gemini schemaで親族・職歴の明細配列を受け取れる。
- promptで情報なしの場合にboolean false、配列 `[]` になる。
- レビューUIで `21.1` が身分事項の正しい位置に出る。
- レビューUIで職歴の有無が申請人に関する情報等の正しい位置に出る。
- 親族・職歴の明細が最大3件まで追加・編集できる。
- 4件目を追加できない、または要手入力扱いになる。
- 通常行と繰り返し専用UIで二重表示されない。
- 空欄明細があっても保存できる。
- 有無false時に明細rowsが `/application-data` に出ない。
- 空欄明細rowsが `/application-data` に出ない。
- Chrome拡張は生成済みrowsだけを入力する。

受け入れ条件:

- 親族・職歴の有無と明細がRASENS順に表示される。
- 親族・職歴の明細を最大3件まで編集できる。
- 空欄のままでも保存できる。
- 配列配下が通常FieldRowと専用UIで二重表示されない。
- backend schema/prompt、canonical docs、frontend UI、mapping/application-data の項目名が一致している。
- 既存の `CaseSummary`、案件一覧、Chrome拡張の案件選択の設計を壊さない。
