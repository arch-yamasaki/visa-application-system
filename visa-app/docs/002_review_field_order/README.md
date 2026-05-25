# レビュー画面フィールド順序設計

レビュー画面（ReviewPage）の左サイドバーに表示するフィールドのセクション構成・順序を、RASENSオンライン申請フォームに準拠して定義する。

## 設計方針

- セクション名・順序はRASENSフォーム（在留資格認定証明書交付申請）の実際の入力画面に合わせる
- セクション内のフィールド順序もRASENSフォームの項目番号（No.）に従う
- Gemini抽出対象外のフィールド（代理人・取次者）もセクションとして表示し、手入力やデフォルト値で対応する
- 内部メタデータ（case_id, workflow_state等）はサイドバーに表示しない

## RASENSフォームのセクション順序（原本）

rasens_offer_fields.json に定義された公式セクション順:

| 順番 | セクション名 | 項目数 | visa-appでの扱い |
|------|-------------|--------|----------------|
| 1 | 申請概要 | 1 | 非表示（在留資格種別は固定値） |
| 2 | 身分事項 | 78 | **表示** |
| 3 | 申請人に関する情報等 | 66 | **表示** |

### 身分事項 78項目の内訳

| No. | 項目群 | 項目数 | 内容 |
|-----|--------|--------|------|
| 1〜8 | 申請人基本情報 | 8 | 国籍、生年月日、氏名、性別、出生地、配偶者、職業、本国居所 |
| 9 | 日本の連絡先 | 6 | 郵便番号、住所、電話、携帯、メール、メール確認 |
| 10 | 旅券 | 2 | 旅券番号、有効期限 |
| 11〜16 | 入国計画 | 9 | 入国目的、予定日、上陸予定港(2)、滞在期間(2)、同伴者、査証申請地 |
| 17 | 出入国歴 | 4 | 有無、回数、直近入国日、直近出国日 |
| 18 | 過去のCOE申請 | 3 | 有無、回数、不交付回数 |
| 19 | 犯罪歴 | 1 | 犯罪を理由とする処分の有無 |
| 20 | 退去強制 | 3 | 有無、回数、直近年月日 |
| **21** | **在日親族及び同居者** | **43** | **有無(1) + 最大6人 × 7属性(続柄、氏名、生年月日、国籍、同居予定、勤務先、在留カード番号)** |
| | **合計** | **78** | |

### 申請人に関する情報等 66項目の内訳

| No. | 項目群 | 項目数 | 内容 |
|-----|--------|--------|------|
| — | 職歴の有無 | 7 | 有無(1) + 国・地域名(6社分) |
| 23 | 最終学歴 | 5 | 区分、詳細区分、その他、学校名、卒業年月日 |
| 24 | 専攻・専門分野 | 4 | 分野(2枠)、その他(2枠) |
| 25 | 情報処理資格 | 2 | 有無、資格名 |
| **26** | **職歴** | **48** | **最大6社 × 8項目(入社月不詳、入社年、入社月、退社月不詳、退社年、退社月、勤務先英字、勤務先漢字)** |
| | **合計** | **66** | |
| 4 | 代理人 | 6 | **表示** |
| 5 | 取次者 | 5 | **表示** |
| 6 | 所属機関に関する情報等 | 54 | **表示** |
| 7 | 高度専門職ポイント表 | 57 | 非表示（技人国では対象外） |
| 8 | 受領方法等 | 3 | 非表示（対象外） |
| 9 | 入力情報確認 | 4 | 非表示（対象外） |

## サイドバーのセクション構成

### セクション1: 身分事項

RASENSフォーム No.1〜21 に対応。申請人の基本情報、旅券、入国計画、出入国歴、在日親族を含む。

| No. | RASENSラベル | visa-appフィールド | データソース | 備考 |
|-----|-------------|-------------------|------------|------|
| 1 | 国籍・地域 | `applicant.nationality` | Gemini抽出 | |
| 2 | 生年月日 | `applicant.date_of_birth` | Gemini抽出 | |
| 3 | 氏名（ローマ字） | `applicant.name_roman` | Gemini抽出 | |
| 4 | 性別 | `applicant.gender` | Gemini抽出 | 抽出漏れが多い |
| 5 | 出生地 | `applicant.place_of_birth` | Gemini抽出 | |
| 6 | 配偶者の有無 | `applicant.marital_status` | Gemini抽出 | |
| 7 | 職業 | `applicant.occupation` | Gemini抽出 | |
| 8 | 本国における居所 | `applicant.home_country_address` | Gemini抽出 | |
| 9 | 日本の連絡先 郵便番号 | `applicant.japan_postal_code` | Gemini抽出 | |
| 9 | 日本の連絡先 住所 | `applicant.japan_address` | Gemini抽出 | |
| 9 | 日本の連絡先 電話番号 | `applicant.japan_phone` | Gemini抽出 | |
| 9 | 日本の連絡先 携帯番号 | `applicant.japan_mobile` | Gemini抽出 | |
| 9 | メールアドレス | `applicant.email` | Gemini抽出 | |
| 10 | 旅券番号 | `passport.number` | Gemini抽出 | |
| 10 | 旅券有効期限 | `passport.expiry_date` | Gemini抽出 | |
| 11 | 入国目的 | `application.purpose_of_entry` | Gemini抽出 | |
| 12 | 入国予定日 | `application.planned_entry_date` | Gemini抽出 | |
| 13 | 上陸予定港 | `application.planned_port` | Gemini抽出 | |
| 14 | 滞在予定期間（年） | `application.planned_period_years` | Gemini抽出 | |
| 14 | 滞在予定期間（月） | `application.planned_period_months` | Gemini抽出 | |
| 15 | 同伴者の有無 | `application.has_accompanying` | Gemini抽出 | |
| 16 | 査証申請予定地 | `application.visa_application_location` | Gemini抽出 | |
| 17 | 過去の出入国歴 有無 | `immigration_history.has_entries` | Gemini抽出 | |
| 17 | 回数 | `immigration_history.entries_count` | Gemini抽出 | |
| 17 | 直近の入国日 | `immigration_history.latest_entry_start` | Gemini抽出 | |
| 17 | 直近の出国日 | `immigration_history.latest_entry_end` | Gemini抽出 | |
| 18 | 過去のCOE申請 有無 | `immigration_history.has_prior_coe` | Gemini抽出 | |
| 18 | 回数 | `immigration_history.prior_coe_count` | Gemini抽出 | |
| 18 | 不交付回数 | `immigration_history.prior_coe_denial_count` | Gemini抽出 | |
| 19 | 犯罪歴 | `immigration_history.has_criminal_record` | Gemini抽出 | |
| 20 | 退去強制・出国命令 有無 | `immigration_history.has_deportation` | Gemini抽出 | |
| 20 | 回数 | `immigration_history.deportation_count` | Gemini抽出 | |
| 20 | 直近の年月日 | `immigration_history.deportation_latest` | Gemini抽出 | |
| 21 | 在日親族 | `family.*` | Gemini抽出 | 将来スコープ |

**含まれるcase_dataトップレベルキー**: `applicant`, `passport`, `application`, `immigration_history`, `family`, `family_in_japan`, `past_history`

### セクション2: 申請人に関する情報等

RASENSフォーム No.23〜26 に対応。学歴、専攻、資格、職歴を含む。

| No. | RASENSラベル | visa-appフィールド | データソース | 備考 |
|-----|-------------|-------------------|------------|------|
| 23 | 最終学歴 区分 | `education.level` | Gemini抽出（S3スコープ） | |
| 23 | 最終学歴 区分詳細 | `education.level_detail` | Gemini抽出 | |
| 23 | 最終学歴 学校名 | `education.school_name` | Gemini抽出 | |
| 23 | 卒業年月日 | `education.graduation_date` | Gemini抽出 | autofill_adapterで日付正規化 |
| 24 | 専攻・専門分野 | `major.field` | Gemini抽出（S3スコープ） | |
| 24 | 専攻 その他 | `major.field_other` | Gemini抽出 | |
| 25 | 情報処理資格 有無 | `it_qualification.has_qualification` | Gemini抽出（S3スコープ） | |
| 25 | 資格名 | `it_qualification.qualification_name` | Gemini抽出 | |
| 26 | 職歴 | `employment_history.*` | 将来実装 | 現在Gemini抽出スコープ外 |

**含まれるcase_dataトップレベルキー**: `education`, `major`, `it_qualification`, `transcript_subjects`, `employment_history`, `qualifications`

### セクション3: 代理人

RASENSフォーム No.27 に対応。在留資格認定証明書交付申請では、申請人（外国人）が海外にいるため、受入れ先企業が代理人として申請するのが一般的。

| No. | RASENSラベル | visa-appフィールド | データソース | 備考 |
|-----|-------------|-------------------|------------|------|
| 27.1 | 氏名 | `proxy.name` | 手入力 | 企業の担当者名 |
| 27.2 | 本人との関係 | `proxy.relationship` | 手入力 / 初期値 | 例: 「雇用先の職員」 |
| 27.3 | 郵便番号 | `proxy.postal_code` | `employer.postal_code` から初期値 | |
| 27.4 | 住所 | `proxy.address` | `employer.address` から初期値 | |
| 27.5 | 電話番号 | `proxy.phone` | `employer.phone` から初期値 | 任意 |
| 27.6 | 携帯電話番号 | `proxy.mobile` | 手入力 | 任意 |

**含まれるcase_dataトップレベルキー**: `proxy`

**特記事項**:
- Gemini抽出対象外。employer情報から初期値を自動生成し、担当者名は手入力。
- 受入れ先企業（雇用主）が代理人となるケースがほとんど。
- 代理人の住所・電話は employer と同一になることが多い。

### セクション4: 取次者

RASENSフォームの取次者セクションに対応。行政書士が申請を取り次ぐ場合に必須。

| 項目 | visa-appフィールド | デフォルト値 | 備考 |
|------|-------------------|------------|------|
| 氏名 | `intermediary.name` | 太田智子 | 設定画面で変更可能 |
| 郵便番号 | `intermediary.postal_code` | 6310845 | |
| 住所 | `intermediary.address` | 奈良県奈良市宝来４丁目１３番７号 | |
| 所属機関等 | `intermediary.organization` | 太田行政書士事務所 | |
| 電話番号 | `intermediary.phone` | 0742405620 | |

**含まれるcase_dataトップレベルキー**: `intermediary`

**特記事項**:
- Gemini抽出対象外。全案件で固定値（太田智子 / 太田行政書士事務所）。
- 将来的にはアカウント設定画面（`/settings`）で管理し、Firestoreに保存する。
- 案件ごとにレビューする必要はないが、サイドバーには表示してフォーム上の存在を確認できるようにする。

### セクション5: 所属機関に関する情報等

RASENSフォーム No.2〜12 に対応。雇用主の基本情報、雇用条件、活動内容を含む。

| No. | RASENSラベル | visa-appフィールド | データソース | 備考 |
|-----|-------------|-------------------|------------|------|
| 2 | 契約の形態 | `contract.contract_type` | Gemini抽出（S2スコープ） | |
| 3.1 | 名称 | `employer.name` | Gemini抽出（S2スコープ） | |
| 3.2 | 法人番号 有無 | `employer.has_corporate_number` | Gemini抽出 | |
| 3.2 | 法人番号 | `employer.corporate_number` | Gemini抽出 | 13桁数字 |
| 3.3 | 支店・事業所名 | `employer.office_name` | Gemini抽出 | |
| 3.4 | 雇用保険適用事業所番号 | `employer.employment_insurance_no` | Gemini抽出 | |
| 3.5 | 業種（主たる業種） | `employer.industry_primary` | Gemini抽出 | |
| 3.6 | 業種 その他 | `employer.industry_other` | Gemini抽出 | |
| 3.9 | 郵便番号 | `employer.postal_code` | Gemini抽出 | |
| 3.10 | 所在地 | `employer.address` | Gemini抽出 | |
| 3.11 | 電話番号 | `employer.phone` | Gemini抽出 | |
| 3.12 | 資本金 | `employer.capital_jpy` | Gemini抽出 | |
| 3.13 | 年間売上高 | `employer.annual_sales_jpy` | Gemini抽出 | |
| 3.14 | 従業員数 | `employer.employee_count` | Gemini抽出 | |
| 3.15 | うち外国人職員数 | `employer.foreign_employee_count` | Gemini抽出 | |
| 3.16 | うち技能実習生 | `employer.technical_intern_count` | Gemini抽出 | |
| 5 | 就労予定期間 区分 | `employment_conditions.employment_period_type` | Gemini抽出 | |
| 5 | 年数 | `employment_conditions.employment_period_years` | Gemini抽出 | |
| 5 | 月数 | `employment_conditions.employment_period_months` | Gemini抽出 | |
| 6 | 雇用開始（入社）年月日 | `employment_conditions.joining_date` | Gemini抽出 | |
| 7 | 月額給与 | `employment_conditions.monthly_salary` | Gemini抽出 | 税引き前 |
| 8 | 実務経験月数 | `employment_conditions.experience_months` | Gemini抽出 | |
| 9 | 役職 有無 | `employment_conditions.has_position` | Gemini抽出 | |
| 9 | 役職名 | `employment_conditions.position_title` | Gemini抽出 | |
| 10 | 職種 | `employment_conditions.job_category_primary` | Gemini抽出 | |
| 11 | 活動内容詳細 | `activity_details.description` | Gemini抽出 | 自由記述 |

**含まれるcase_dataトップレベルキー**: `employer`, `employment_conditions`, `employment_terms`, `employment_contract`, `contract`, `activity_details`

## 非表示セクション

以下はサイドバーに表示しない:

| セクション | 理由 |
|-----------|------|
| 申請概要 | 在留資格種別は固定値（技人国）。case_id, workflow_state等は内部メタデータ |
| 高度専門職ポイント表 | 技人国では対象外 |
| 受領方法等 | 技人国の初期MVPでは対象外 |
| 入力情報確認 | フォーム確認画面でありデータ項目ではない |
| 審査 | AI内部の品質指標。ReviewBannerの「要対応」で代替 |

## case_dataキー → セクション マッピング

fieldPaths.ts の `sectionMap` に設定する対応表:

| case_dataキー | セクション |
|--------------|-----------|
| `applicant` | 身分事項 |
| `passport` | 身分事項 |
| `application` | 身分事項 |
| `immigration_history` | 身分事項 |
| `family` | 身分事項 |
| `family_in_japan` | 身分事項 |
| `past_history` | 身分事項 |
| `education` | 申請人に関する情報等 |
| `major` | 申請人に関する情報等 |
| `it_qualification` | 申請人に関する情報等 |
| `transcript_subjects` | 申請人に関する情報等 |
| `employment_history` | 申請人に関する情報等 |
| `qualifications` | 申請人に関する情報等 |
| `proxy` | 代理人 |
| `intermediary` | 取次者 |
| `employer` | 所属機関に関する情報等 |
| `employment_conditions` | 所属機関に関する情報等 |
| `employment_terms` | 所属機関に関する情報等 |
| `employment_contract` | 所属機関に関する情報等 |
| `contract` | 所属機関に関する情報等 |
| `activity_details` | 所属機関に関する情報等 |

`case`, `assessments`, `supporting_documents`, `review` はマッピングしない（非表示）。

## SECTION_ORDER

```typescript
export const SECTION_ORDER = [
  '身分事項',
  '申請人に関する情報等',
  '代理人',
  '取次者',
  '所属機関に関する情報等',
]
```

SECTION_ORDERに含まれないセクションは末尾の「その他」として表示。

## 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `frontend/src/lib/fieldPaths.ts` | sectionMap、SECTION_ORDER を本設計に合わせて更新 |
| `frontend/src/components/review/FieldPanel.tsx` | SECTION_ORDER に基づくソート（変更済みの場合は確認のみ） |
