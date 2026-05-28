# RASENSフォーム設計台帳

## 目的

この文書は、RASENS申請フォームの項目順を基準に、visa-app が各項目をどう扱うかを決めるための台帳です。

単なるレビュー画面の表示順ではなく、次を1行ずつ見えるようにします。

- visa-app のレビュー画面に表示するか
- Firestore `case_data` のどこに保存するか
- Geminiで抽出するか、人が入力するか、固定値にするか
- Chrome拡張の `application_data.rows` に変換するか
- MVPでは対象外にするか

正本データ構造は [canonical_case_data_v2.md](canonical_case_data_v2.md) に置きます。この文書は、その canonical path を RASENSフォーム順に並べ、レビューUI・自動入力・将来対応の扱いを整理します。

## 重要な前提

### 画面番号はIDではない

RASENS画面に表示される番号は、人間がフォーム上の位置を探すための参考情報です。セクションごとに番号が再利用され、同じ `2` や `11` が複数回出ます。

そのため、この文書では `RASENS No.` という名前を使わず、`画面番号（参考）` と呼びます。

| 情報 | 役割 | 技術キーとして使うか |
|---|---|---|
| `canonical path` | visa-app内部の正本キー | する |
| `field_id` / `field_name` | RASENS DOM入力先 | DOM操作では使うが、業務IDではない |
| `画面番号（参考）` | RASENS画面上の番号・見出し | しない |
| `RASENS表示名` | 人間向けラベル | しない |
| フォーム上の出現順 | レビュー画面や台帳の並び順 | IDではない。フォーム台帳内の並び順としてのみ使う |

### フォーム物理情報はcase_dataに入れない

`case_data` は意味上の申請データだけを持ちます。`item[187].textData`, `select_256101`, `tr_256101` のような RASENS画面の物理情報は、`case_data` ではなく mapping / application-data 生成側で扱います。

## 台帳の列

今後この文書で使う表は、次の列を基本形にします。

| 列 | 意味 |
|---|---|
| フォーム順 | RASENS画面に出てくる順。人間向けの並び順で、永続IDではない |
| セクション | RASENS上の大きなまとまり |
| 画面番号（参考） | RASENS画面に表示される番号・見出し。IDではない |
| RASENS表示名 | RASENS画面に出る項目名 |
| visa-app表示 | レビュー画面での扱い |
| canonical path | Firestore `case_data` の保存先 |
| 入力方針 | 値をどう作るか |
| application mapping | Chrome拡張投入行に変換するか |
| 備考 | 条件付き、繰り返し、MVP対象外、要確認など |

## 扱いの値

### visa-app表示

| 値 | 意味 |
|---|---|
| 表示 | レビュー画面の通常フィールドとして表示する |
| 表示候補 | MVPで表示する可能性が高いが、UI設計や抽出精度の確認が必要 |
| 別UI | 一覧、書類、設定、確認バナーなど、通常フィールド以外で扱う |
| 非表示 | `case_data` には持つが、初期MVPのレビュー行には出さない |
| 将来対応 | 初期MVPでは扱わないが、後で設計する |
| 非対応 | 技人国MVPの対象外 |

### 入力方針

| 値 | 意味 |
|---|---|
| Gemini抽出 | 書類からAIで抽出する |
| Gemini抽出+人確認 | AIで抽出するが、人の確認を強く前提にする |
| 人入力 | レビュー画面で人が入力する |
| 固定値 | 技人国MVPでは固定できる値 |
| 設定値 | 申請会社・取次者・運用設定から初期化する |
| 派生 | 他の `case_data` から生成する |
| 非対応 | 初期MVPでは値を作らない |

### application mapping

| 値 | 意味 |
|---|---|
| あり | 新canonical pathで投入対象として設計済み。実装時にmapping/generatorで検証する |
| 条件付き | `visible_when` や選択肢によって出す場合だけ生成する |
| 予定 | 必要だが mapping が未整備 |
| なし | Chrome拡張で入力しない |
| 手動 | RASENS画面上で人が操作する |
| 要検証 | mappingはあるが、フォーム台帳との突合で疑いがある |

## RASENSセクション全体

`rasens_offer_fields.json` の現在の台帳では、RASENSフォームは274行です。初期MVPでは全項目をレビュー・抽出・自動入力するのではなく、技人国COEに必要な範囲から扱います。

ただし、台帳としては274行すべてに扱いを付けます。自動投入するのはMVP対象だけですが、自動投入しない行も `手入力`, `設定値`, `派生`, `非対応`, `将来対応` のように分類し、未調査のまま放置しない方針です。

| フォーム順 | セクション | 項目数 | visa-appでの扱い | 備考 |
|---:|---|---:|---|---|
| 1 | 申請概要 | 1 | 非表示 / 固定値 | 主たる活動内容。活動内容詳細ではなく、フォーム全体の大分類select |
| 2 | 身分事項 | 78 | 表示 | 申請人、旅券、入国予定、出入国歴、家族情報 |
| 3 | 申請人に関する情報等 | 66 | 表示 | 学歴、専攻、資格、職歴 |
| 4 | 代理人 | 6 | 表示候補 | `proxy`。受入企業側の担当者。住所・電話は会社情報から初期化候補、氏名は人入力中心 |
| 5 | 取次者 | 5 | 非表示 / 設定値 | `intermediary`。太田さん側の申請アカウントを持つ申請会社情報。案件ごとの抽出対象ではない |
| 6 | 所属機関に関する情報等 | 54 | 表示 | 雇用会社、契約、給与、職務内容 |
| 7 | 高度専門職ポイント表 | 57 | 非対応 | 技人国MVPでは対象外 |
| 8 | 受領方法等 | 3 | 非表示 / 将来対応 | 運用が固まったら別UIまたは設定値 |
| 9 | 入力情報確認 | 4 | 非対応 | RASENS確認画面の操作であり、`case_data` ではない |

現行mappingの一致状況はおおまかに次の通りです。これは旧pathを含む実装済み範囲の確認用であり、新canonical pathでの整備完了を意味しません。

| セクション | 現行mapping一致数 / フォーム項目数 | コメント |
|---|---:|---|
| 申請概要 | 1 / 1 | 主たる活動内容 |
| 身分事項 | 33 / 78 | 基本情報は多く対応済み。旅券・出入国歴・家族は canonical では `applicant.*` 配下に寄せる |
| 申請人に関する情報等 | 7 / 66 | 学校名・卒業日・職歴の一部のみ。学歴・職歴・資格は canonical では `applicant.*` 配下に寄せる |
| 代理人 | 0 / 6 | 手入力・派生初期値として設計する |
| 取次者 | 0 / 5 | 設定値として設計する |
| 所属機関に関する情報等 | 13 / 54 | `employer.*` / `employment.*` 中心。会社情報と今回の就労条件を分ける |
| 高度専門職ポイント表 | 8 / 57 | 技人国MVPでは対象外。現行mappingの誤参照疑いを含む |
| 受領方法等 | 0 / 3 | 運用確定後 |
| 入力情報確認 | 0 / 4 | case_data対象外 |

### mappingの注意

旧 `rasens_offer_mapping.json` は削除済みです。`rasens_offer_mapping_v2.json` は canonical v2 と `rasens_offer_fields.json` の `field_id` / `field_name` を照合したMVP自動投入対象として管理します。

特に所属機関まわりはフォーム台帳との照合を必須にします。旧mappingでは `field_id` と `field_name` が別項目を指す疑いがあり、値を別欄へ投入するリスクがありました。backend generator は mapping target がフォーム台帳に存在することを確認します。

canonical v2 では、mapping、`transform`、`visible_when` の評価は backend に集約します。Chrome拡張は `application_data.rows` を受け取り、`field_id` / `field_name` でDOM入力するだけにします。

## MVP詳細台帳

この表は、初期MVPで扱う主要項目の設計案です。フォーム順は `rasens_offer_fields.json` の出現順を基準にします。親族明細や職歴のような繰り返し項目は、複数のRASENS行を1つの配列項目として集約しているため、代表行または開始位置を置きます。

### 1. 申請概要

| フォーム順 | 画面番号（参考） | RASENS表示名 | visa-app表示 | canonical path | 入力方針 | application mapping | 備考 |
|---:|---|---|---|---|---|---|---|
| 1 | なし | 主たる活動内容 | 非表示 | `entry_plan.main_activity_category` | 固定値 | あり | 申請概要の大分類select。技人国COEでは「技術・人文知識・国際業務」相当を選択。活動内容詳細ではない |

### 2. 身分事項

| フォーム順 | 画面番号（参考） | RASENS表示名 | visa-app表示 | canonical path | 入力方針 | application mapping | 備考 |
|---:|---|---|---|---|---|---|---|
| 2 | 1 | 国籍・地域 | 表示 | `applicant.nationality_region` | Gemini抽出 | あり | パスポート等から抽出 |
| 3 | 2 | 生年月日 | 表示 | `applicant.birth_date` | Gemini抽出 | あり | 日付正規化が必要 |
| 4 | 3 | 氏名 | 表示 | `applicant.name_roman` | Gemini抽出 | あり | 旅券表記、大文字、スペース区切り |
| 5 | 4 | 性別 | 表示 | `applicant.sex` | Gemini抽出+人確認 | あり | 選択肢へ正規化 |
| 6 | 5 | 出生地 | 表示 | `applicant.birth_place` | Gemini抽出 | あり | 旧path `place_of_birth` は使わない |
| 7 | 6 | 配偶者の有無 | 表示 | `applicant.marital_status` | Gemini抽出+人確認 | あり | 選択肢へ正規化 |
| 8 | 7 | 職業 | 表示 | `applicant.occupation` | Gemini抽出 | あり | 書類にない場合は人入力 |
| 9 | 8 | 本国における居住地 | 表示 | `applicant.home_country_address` | Gemini抽出 | あり | 現住所と混同しない |
| 10 | 9.1 | 日本における連絡先 郵便番号 | 表示 | `applicant.japan_contact.postal_code` | Gemini抽出+人確認 | あり | 不明時の扱いは運用ルール化 |
| 11 | 9.2 | 日本における連絡先 居住地 | 表示 | `applicant.japan_contact.address` | Gemini抽出+人確認 | あり | 旧path `applicant.japan_address` は使わない |
| 12 | 9.3 | 日本における連絡先 電話番号 | 表示 | `applicant.japan_contact.phone` | Gemini抽出+人確認 | あり | 携帯とのどちらか必須 |
| 13 | 9.4 | 日本における連絡先 携帯電話番号 | 表示 | `applicant.japan_contact.mobile` | Gemini抽出+人確認 | あり | 電話とのどちらか必須 |
| 14 | 9.5 | メールアドレス | 表示 | `applicant.japan_contact.email` | Gemini抽出+人確認 | あり | 連絡先として要確認 |
| 15 | 10.1 | 旅券番号 | 表示 | `applicant.passport.number` | Gemini抽出 | あり | 旅券は独立top-levelにせず申請人配下で保持 |
| 16 | 10.2 | 旅券有効期限 | 表示 | `applicant.passport.expiry_date` | Gemini抽出 | あり | 入国予定日との整合性確認 |
| 17 | 11 | 入国目的 | 表示 | `entry_plan.purpose_of_entry` | 固定値 / 人確認 | あり | 身分事項 No.11 のselect。画像で確認した項目。主たる活動内容とは別select |
| 18 | 12 | 入国予定年月日 | 表示 | `entry_plan.planned_entry_date` | Gemini抽出+人確認 | あり | 日付正規化が必要 |
| 19 | 13.1 | 上陸予定港 | 表示 | `entry_plan.planned_port` | 人入力 | あり | 書類から取れないことが多い |
| 20 | 13.2 | 上陸予定港 その他 | 表示候補 | `entry_plan.planned_port_other` | 人入力 | 条件付き | その他選択時のみ |
| 21 | 14.1 | 滞在予定期間 年 | 表示 | `entry_plan.planned_period_years` | 人入力 | あり | 希望期間として確認 |
| 22 | 14.2 | 滞在予定期間 月 | 表示 | `entry_plan.planned_period_months` | 人入力 | あり | 希望期間として確認 |
| 23 | 15 | 同伴者の有無 | 表示 | `applicant.family.has_accompanying_members` | Gemini抽出+人確認 | あり | 旧path `application.has_accompanying` / `family.has_accompanying_members` は使わない |
| 24 | 16 | 査証申請予定地 | 表示 | `entry_plan.visa_application_location` | 人入力 | あり | 在外公館名等 |
| 25 | 17.1 | 過去の出入国歴 有無 | 表示 | `applicant.immigration_history.has_entries` | Gemini抽出+人確認 | あり | 履歴書等で確認 |
| 26 | 17.2 | 過去の出入国歴 回数 | 表示 | `applicant.immigration_history.entries_count` | Gemini抽出+人確認 | あり | 有の場合のみ |
| 27 | 17.3 | 直近の出入国歴 始期 | 表示 | `applicant.immigration_history.latest_entry.start_date` | Gemini抽出+人確認 | あり | 有の場合のみ |
| 28 | 17.4 | 直近の出入国歴 終期 | 表示 | `applicant.immigration_history.latest_entry.end_date` | Gemini抽出+人確認 | あり | 有の場合のみ |
| 29 | 18.1 | 過去のCOE申請歴 有無 | 表示 | `applicant.immigration_history.prior_coe_applications.has_history` | Gemini抽出+人確認 | あり | COE履歴 |
| 30 | 18.2 | 過去のCOE申請歴 回数 | 表示 | `applicant.immigration_history.prior_coe_applications.count` | Gemini抽出+人確認 | あり | 有の場合のみ |
| 31 | 18.3 | 不交付回数 | 表示 | `applicant.immigration_history.prior_coe_applications.denial_count` | Gemini抽出+人確認 | あり | 審査リスクとして重要 |
| 32 | 19 | 犯罪歴 | 表示 | `applicant.immigration_history.criminal_record` | Gemini抽出+人確認 | あり | 必ず人確認 |
| 33 | 20.1 | 退去強制・出国命令歴 有無 | 表示 | `applicant.immigration_history.deportation_or_departure_order` | Gemini抽出+人確認 | 予定 | 必ず人確認 |
| 34 | 20.2 | 退去強制・出国命令歴 回数 | 表示 | `applicant.immigration_history.deportation_count` | Gemini抽出+人確認 | 予定 | 有の場合のみ |
| 35 | 20.3 | 直近の送還年月日 | 表示 | `applicant.immigration_history.deportation_latest` | Gemini抽出+人確認 | 予定 | 有の場合のみ |
| 36 | 21.1 | 在日親族及び同居者 有無 | 表示 | `applicant.family.has_japan_relatives_or_cohabitants` | Gemini抽出+人確認 | あり | 詳細行の表示条件 |
| 37 | 21.2 | 在日親族及び同居者 続柄 | 折りたたみ内 | `applicant.family.japan_relatives_or_cohabitants[0..2].relationship` | Gemini抽出+人確認 | あり | 最大3件。RASENS番号は各枠で重複するため参考番号 |
| 38 | 21.3 | 在日親族及び同居者 氏名 | 折りたたみ内 | `applicant.family.japan_relatives_or_cohabitants[0..2].name` | Gemini抽出+人確認 | あり | 空欄行はrowsに出さない |
| 39 | 21.4 | 在日親族及び同居者 生年月日 | 折りたたみ内 | `applicant.family.japan_relatives_or_cohabitants[0..2].birth_date` | Gemini抽出+人確認 | あり | 生年月日の精度radioは後続QAで確認 |
| 40 | 21.5 | 在日親族及び同居者 国籍・地域 | 折りたたみ内 | `applicant.family.japan_relatives_or_cohabitants[0..2].nationality_region` | Gemini抽出+人確認 | あり | RASENS選択肢に合わせる |
| 41 | 21.6 | 在日親族及び同居者 同居予定の有無 | 折りたたみ内 | `applicant.family.japan_relatives_or_cohabitants[0..2].will_cohabit` | Gemini抽出+人確認 | あり | boolean |
| 42 | 21.7 | 在日親族及び同居者 勤務先・通学先 | 折りたたみ内 | `applicant.family.japan_relatives_or_cohabitants[0..2].workplace_or_school_name` | Gemini抽出+人確認 | あり |  |
| 43 | 21.8 | 在日親族及び同居者 在留カード番号等 | 折りたたみ内 | `applicant.family.japan_relatives_or_cohabitants[0..2].residence_card_or_certificate_number` | Gemini抽出+人確認 | あり |  |

### 3. 申請人に関する情報等

| フォーム順 | 画面番号（参考） | RASENS表示名 | visa-app表示 | canonical path | 入力方針 | application mapping | 備考 |
|---:|---|---|---|---|---|---|---|
| 80 | 23.1 | 最終学歴 本邦・外国区分 | 表示 | `applicant.education[0].country_type` | Gemini抽出 | あり | `applicant.education[0]` を最終学歴として使う |
| 81 | 23.2 | 最終学歴 区分 | 表示 | `applicant.education[0].level` | Gemini抽出 | あり | 学校種別の選択肢 |
| 82 | 23.3 | 最終学歴 その他 | 表示候補 | `applicant.education[0].level_other` | 人入力 | 条件付き | その他選択時のみ |
| 83 | 23.4 | 学校名 | 表示 | `applicant.education[0].school_name` | Gemini抽出 | あり | 卒業証明書等 |
| 84 | 23.5 | 卒業年月日 | 表示 | `applicant.education[0].graduation_date` | Gemini抽出 | あり | 日付正規化 |
| 85 | 24.1 | 専攻・専門分野 | 表示 | `applicant.education[0].major_field` | Gemini抽出+人確認 | 予定 | 職務内容との整合性確認に使う |
| 86 | 24.2 | 専攻・専門分野 その他 | 表示候補 | `applicant.education[0].major_field_other` | 人入力 | 条件付き | その他選択時のみ |
| 89 | 25.1 | 情報処理資格 有無 | 表示 | `applicant.qualifications.it.has_qualification` | Gemini抽出+人確認 | 予定 | RASENSの情報処理資格欄に対応 |
| 90 | 25.2 | 情報処理資格 名称 | 表示候補 | `applicant.qualifications.it.qualification_name` | Gemini抽出+人確認 | 条件付き | 有の場合のみ。その他資格は `applicant.qualifications.items[]` に保持 |
| 91 | なし | 職歴の有無 | 表示 | `applicant.has_employment_history` | Gemini抽出+人確認 | あり | 詳細行の表示条件 |
| 92 | 国・地域名 | 職歴 国・地域名 | 折りたたみ内 | `applicant.employment_history[0..2].country_region` | Gemini抽出+人確認 | あり | 最大3件 |
| 93 | 26.1 | 職歴 入社月不詳 | 折りたたみ内 | `applicant.employment_history[0..2].start_month_unknown` | Gemini抽出+人確認 | あり | 年月が分かる場合はfalse |
| 94 | 26.2 | 職歴 入社年月 | 折りたたみ内 | `applicant.employment_history[0..2].start_date` | Gemini抽出+人確認 | あり | `YYYY-MM`または`YYYYMM`相当 |
| 95 | 26.3 | 職歴 退社月不詳 | 折りたたみ内 | `applicant.employment_history[0..2].end_month_unknown` | Gemini抽出+人確認 | あり | 在職中/未記載時は人確認 |
| 96 | 26.4 | 職歴 退社年月 | 折りたたみ内 | `applicant.employment_history[0..2].end_date` | Gemini抽出+人確認 | あり |  |
| 97 | 26.5 | 職歴 勤務先名称(英字表記) | 折りたたみ内 | `applicant.employment_history[0..2].company_name_en` | Gemini抽出+人確認 | あり |  |
| 98 | 26.6 | 職歴 勤務先名称(漢字表記) | 折りたたみ内 | `applicant.employment_history[0..2].company_name_local` | Gemini抽出+人確認 | あり | 現地語表記。日本語限定ではない |

### 4. 代理人

| フォーム順 | 画面番号（参考） | RASENS表示名 | visa-app表示 | canonical path | 入力方針 | application mapping | 備考 |
|---:|---|---|---|---|---|---|---|
| 48 | 27.1 | 氏名 | 表示候補 | `proxy.name` | 人入力 | 予定 | 受入企業側の担当者。会社名ではない |
| 49 | 27.2 | 本人との関係 | 表示候補 | `proxy.relationship` | 固定値 / 人入力 | 予定 | 受入機関職員など |
| 50 | 27.3 | 郵便番号 | 表示候補 | `proxy.postal_code` | 派生 / 人入力 | 予定 | `employer.postal_code` から初期化候補 |
| 51 | 27.4 | 住所 | 表示候補 | `proxy.address` | 派生 / 人入力 | 予定 | `employer.address` から初期化候補 |
| 52 | 27.5 | 電話番号 | 表示候補 | `proxy.phone` | 派生 / 人入力 | 予定 | `employer.phone` から初期化候補 |
| 53 | 27.6 | 携帯電話番号 | 表示候補 | `proxy.mobile` | 人入力 | 予定 | 任意または運用確認 |

### 5. 取次者

| フォーム順 | 画面番号（参考） | RASENS表示名 | visa-app表示 | canonical path | 入力方針 | application mapping | 備考 |
|---:|---|---|---|---|---|---|---|
| 54 | 取次者 | 氏名 | 非表示 | `settings.intermediary.name` | 設定値 | あり | 太田さん側の申請アカウントを持つ申請会社情報から注入 |
| 55 | 取次者 | 郵便番号 | 非表示 | `settings.intermediary.postal_code` | 設定値 | あり | 案件ごとの抽出対象ではない |
| 56 | 取次者 | 住所 | 非表示 | `settings.intermediary.address` | 設定値 | あり | 案件ごとの抽出対象ではない |
| 57 | 取次者 | 所属機関等 | 非表示 | `settings.intermediary.organization` | 設定値 | あり | 申請アカウントを持つ申請会社名 |
| 58 | 取次者 | 電話番号 | 非表示 | `settings.intermediary.phone` | 設定値 | あり | 案件ごとの抽出対象ではない |

### 6. 所属機関に関する情報等

| フォーム順 | 画面番号（参考） | RASENS表示名 | visa-app表示 | canonical path | 入力方針 | application mapping | 備考 |
|---:|---|---|---|---|---|---|---|
| 157 | 2 | 契約の形態 | 表示 | `employment.contract_type` | Gemini抽出+人確認 | 予定 | 会社属性ではなく今回の申請人と所属機関の関係 |
| 158 | 3.1 | 名称 | 表示 | `employer.name` | Gemini抽出 | あり | 所属機関名 |
| 159 | 3.2 | 法人番号 有無 | 表示 | `employer.has_corporate_number` | Gemini抽出+人確認 | 予定 | 法人番号とのセット |
| 160 | 3.2 | 法人番号 | 表示 | `employer.corporate_number` | Gemini抽出 | あり | 有の場合のみ |
| 161 | 3.3 | 支店・事業所名 | 表示候補 | `employer.office_name` | Gemini抽出+人確認 | あり | 本社のみの場合は空 |
| 162 | 3.4 | 雇用保険適用事業所番号 | 表示 | `employer.employment_insurance_office_number` | Gemini抽出+人確認 | あり | 旧path `employment_insurance_no` は使わない |
| 163 | 3.5 | 主たる業種 | 表示 | `employer.industry_primary` | Gemini抽出+人確認 | あり | 選択肢へ正規化 |
| 164 | 3.6 | 業種 その他 | 表示候補 | `employer.industry_other` | 人入力 | 条件付き | その他選択時のみ |
| 169 | 3.9 | 郵便番号 | 表示 | `employer.postal_code` | Gemini抽出+人確認 | 要確認 | 現行mappingの参照先に誤り疑いあり |
| 170 | 3.10 | 所在地 | 表示 | `employer.address` | Gemini抽出 | あり | 会社所在地 |
| 171 | 3.11 | 電話番号 | 表示 | `employer.phone` | Gemini抽出+人確認 | あり | 会社電話番号 |
| 172 | 3.12 | 資本金 | 表示 | `employer.capital_jpy` | Gemini抽出+人確認 | あり | 数値正規化 |
| 173 | 3.13 | 年間売上高 | 表示 | `employer.annual_sales_jpy` | Gemini抽出+人確認 | あり | 数値正規化 |
| 174 | 3.14 | 従業員数 | 表示 | `employer.employee_count` | Gemini抽出+人確認 | あり | 数値正規化 |
| 175 | 3.15 | うち外国人職員数 | 表示 | `employer.foreign_employee_count` | Gemini抽出+人確認 | あり | 数値正規化 |
| 176 | 3.16 | うち技能実習生数 | 表示 | `employer.technical_intern_count` | Gemini抽出+人確認 | あり | 数値正規化 |
| 179 | 5.1 | 就労予定期間 区分 | 表示 | `employment.employment_period_type` | Gemini抽出+人確認 | 予定 | 有期/無期等 |
| 180 | 5.2 | 就労予定期間 年 | 表示 | `employment.employment_period_years` | Gemini抽出+人確認 | 予定 | 有期の場合 |
| 181 | 5.3 | 就労予定期間 月 | 表示 | `employment.employment_period_months` | Gemini抽出+人確認 | 予定 | 有期の場合 |
| 182 | 6 | 雇用開始年月日 | 表示 | `employment.joining_date` | Gemini抽出 | 予定 | 日付正規化 |
| 183 | 7 | 月額給与 | 表示 | `employment.monthly_salary` | Gemini抽出+人確認 | 予定 | 金額は円前提。手当込み/なしの運用確認 |
| 184 | 8 | 実務経験月数 | 表示 | `employment.experience_months` | Gemini抽出+人確認 | 予定 | 学歴要件との関係で確認 |
| 185 | 9.1 | 役職 有無 | 表示 | `employment.has_position` | Gemini抽出+人確認 | 予定 | 役職名とのセット |
| 186 | 9.2 | 役職名 | 表示候補 | `employment.position_title` | Gemini抽出+人確認 | 条件付き | 有の場合のみ |
| 187 | 10 | 職種 | 表示 | `employment.job_category_primary` | Gemini抽出+人確認 | 予定 | 選択肢へ正規化 |
| 188 | 11 | 活動内容詳細 | 表示 | `employment.activity_details` | Gemini抽出+人編集 | あり | 所属機関セクションの600文字textarea。主たる活動内容・入国目的とは別物 |

## 非表示または別UIで扱う項目

| 項目 | 扱い | 理由 |
|---|---|---|
| `case.*` | 別UI | 内部メタデータ。レビュー行ではなく画面ヘッダーや状態表示で扱う |
| `field_metadata` | 別UI | 根拠表示用。入力値ではない |
| `review` | 別UI | ReviewBanner / 不足・警告表示で扱う |
| `supporting_documents` | 別UI | 書類一覧・不足確認UIで扱う |
| `assessments` | 別UI | 判定サマリーで扱う |
| 高度専門職ポイント表 | 非対応 | 技人国MVPでは対象外 |
| 受領方法等 | 将来対応 | 運用が固まったら `receiving_method` として設計 |
| 入力情報確認 | 非対応 | RASENS確認画面の操作であり、case_data正本ではない |

## 実装への反映

`frontend/src/lib/fieldPaths.ts` は次の形へ寄せます。

- `sectionMap` から旧aliasを削除する。
- `SECTION_ORDER` をこの文書の順序に合わせる。
- `labelOverrides` は canonical path のみを正にする。
- 旧pathを一時的に表示する必要がある場合は、migration期間だけ `legacy` コメント付きで隔離する。

`rasens_offer_mapping_v2.json` と backend generator は次を満たすようにします。

- `画面番号（参考）` を技術的なキーとして使わない。
- `field_id` / `field_name` は `rasens_offer_fields.json` と照合する。
- `canonical path` が `canonical_case_data_v2.md` と `frontend/src/types/caseData.ts` に存在することを検証する。
- `employer.postal_code` のような誤った物理項目参照を検出する。
- 274行台帳上で、MVP自動投入対象以外にも `手入力`, `設定値`, `非対応`, `将来対応` の扱いを明示する。
- `transform` と `visible_when` は backend generator だけで評価する。

削除対象の旧path例:

- `applicant.nationality`
- `applicant.date_of_birth`
- `applicant.gender`
- `applicant.japan_address`
- `application.has_accompanying`
- `immigration_history.has_criminal_record`
- `activity_details.description`
- `passport.number`
- `passport.expiry_date`
- `family.*`
- `education.*`
- `employment_history.*`
- `contract.contract_type`
- `employment_conditions.*`
- `application.activity_details`
- `employment_terms`
- `employment_contract`
- `family_in_japan`
- `past_history`
