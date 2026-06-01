# Canonical Case Data v2

## 結論

Firestore の `cases/{case_id}` を visa-app の案件正本にします。

`case_data` は値だけを持つ canonical data とし、Geminiの抽出根拠やRASENSの物理フィールド名は入れません。根拠は `field_metadata`、レビュー判断は `review`、Chrome拡張投入データはAPIで生成する派生物として分離します。

top-level section は増やしすぎません。初期MVPでは、意味が大きく違うものだけを top-level に置きます。

```text
case_data
  case          # 案件・申請種別
  applicant     # 申請人本人と本人に紐づく履歴・家族・学歴・資格
  entry_plan    # 今回の入国・申請計画
  employer      # 所属機関そのもの
  employment    # 今回の契約・就労条件・活動内容
  proxy         # 代理人
  intermediary  # 取次者
  receiving_method
```

`passport`, `contract`, `activity_details`, `family`, `education`, `employment_history`, `qualifications` は原則として独立top-levelにしません。申請人に属するものは `applicant.*`、今回の雇用・活動に属するものは `employment.*` に寄せます。

`case_data.applicant` は、この案件時点の申請人スナップショットです。将来、同一人物の複数案件を横断管理する `persons/{person_id}` を作る場合でも、RASENS投入に使う値は各 `cases/{case_id}.case_data.applicant` に固定します。

## Data Flow

```text
Gemini raw extraction
  -> normalize
Firestore cases/{case_id}
  - case_data        canonical value-only data
  - field_metadata   evidence keyed by canonical path
  - review           structured review result
  - document_manifest
  -> generate
application_data rows
  -> Chrome extension
```

## Firestore CaseDocument v2

```json
{
  "case_id": "case_xxx",
  "schema_version": "2.0",
  "workflow_state": "extracted",
  "created_at": "2026-05-25T10:00:00+09:00",
  "updated_at": "2026-05-25T10:05:00+09:00",
  "case_data": {},
  "field_metadata": {},
  "review": {},
  "document_manifest": { "documents": [] },
  "extraction": {
    "engine": "gemini",
    "model": "gemini-3-flash-preview",
    "run_id": "run_xxx",
    "raw_stored": false
  }
}
```

| field | 役割 |
|---|---|
| `case_id` | Firestore document id と同一 |
| `schema_version` | case document全体のスキーマ版 |
| `workflow_state` | UI/拡張が参照する状態 |
| `case_data` | 入力値の正本 |
| `field_metadata` | 抽出根拠・人手編集情報 |
| `review` | 不足・矛盾・人判断の理由 |
| `document_manifest` | アップロード書類一覧 |
| `extraction` | 抽出エンジン・run情報。rawを保存する場合も正本ではない |

## workflow_state

初期MVPでは次に絞ります。

| state | 意味 |
|---|---|
| `draft` | ケース作成直後 |
| `extracting` | AI抽出中 |
| `extracted` | 抽出結果が保存され、レビュー画面で確認・編集できる |
| `failed` | 抽出失敗 |

`needs_review`、`ready_to_fill`、`extraction_failed`、`launch_failed` は移行互換として読み取るだけにし、新規保存値としては増やしません。

`filled` や `submitted` は、RASENS側の最終操作を自動化しない限り初期MVPでは使いません。

## case_data

`case_data` は、RASENSの意味体系には寄せますが、画面の物理IDには寄せません。

## Gemini extraction value types

Gemini の `response_schema` は、まず影響が小さい範囲だけ typed にします。
保存前normalizeは入れず、Gemini schema と prompt で型を制約します。

| field kind | Gemini `FieldValue.value` | 備考 |
|---|---|---|
| boolean | JSON boolean | `has_*`, `criminal_record`, `has_corporate_number`, `has_position` など |
| small count | JSON integer | 入出国回数、COE申請回数、不交付回数、退去強制等の回数 |
| date | string | 当面は `YYYY-MM-DD` 文字列。UI編集と既存データの安定後に再検討 |
| money / employee count | string | 単位・桁区切り・資料表記ゆれがあるため当面維持 |
| free text / select label | string | RASENS投入値は `application_data` 生成時に変換 |

BOOLEAN / INTEGER の `value` には空文字やnullを使いません。書類上の明確な記載がないbooleanは、各項目の既定方針に従って `false` を使います。回数系は該当なしなら `0` を使います。

```json
{
  "schema_version": "2.0",
  "case": {
    "case_id": "case_xxx",
    "application_type": "certificate_of_eligibility",
    "target_status": "engineer_humanities_international",
    "intake_channel": "employer"
  },
  "applicant": {
    "nationality_region": "Nepal",
    "birth_date": "1998-01-01",
    "name_roman": "TARO SAMPLE",
    "sex": "male",
    "birth_place": "Kathmandu",
    "marital_status": "single",
    "occupation": "Engineer",
    "home_country_address": "Kathmandu, Nepal",
    "japan_contact": {
      "postal_code": "",
      "address": "",
      "phone": "",
      "mobile": "",
      "email": ""
    },
    "passport": {
      "number": "PA0000000",
      "expiry_date": "2030-01-01"
    },
    "immigration_history": {
      "has_entries": false,
      "entries_count": 0,
      "latest_entry": {
        "start_date": "",
        "end_date": ""
      },
      "prior_coe_applications": {
        "has_history": false,
        "count": 0,
        "denial_count": 0
      },
      "criminal_record": false,
      "deportation_or_departure_order": false
    },
    "family": {
      "has_accompanying_members": false,
      "has_japan_relatives_or_cohabitants": false,
      "japan_relatives_or_cohabitants": []
    },
    "education": [
      {
        "level": "",
        "school_name": "",
        "graduation_date": "",
        "major_field": ""
      }
    ],
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
    ],
    "qualifications": {
      "it": {
        "has_qualification": false,
        "qualification_name": ""
      },
      "items": []
    }
  },
  "entry_plan": {
    "main_activity_category": "技術・人文知識・国際業務",
    "purpose_of_entry": "技術・人文知識・国際業務",
    "planned_entry_date": "",
    "planned_port": "",
    "planned_port_other": "",
    "planned_period_years": "",
    "planned_period_months": "",
    "visa_application_location": ""
  },
  "employer": {
    "name": "",
    "has_corporate_number": true,
    "corporate_number": "",
    "representative_name": "",
    "representative_title": "",
    "office_name": "",
    "employment_insurance_office_number": "",
    "industry_primary": "",
    "industry_other": "",
    "postal_code": "",
    "address": "",
    "phone": "",
    "capital_jpy": "",
    "annual_sales_jpy": "",
    "employee_count": "",
    "foreign_employee_count": "",
    "technical_intern_count": ""
  },
  "employment": {
    "contract_type": "",
    "job_title": "",
    "work_location": "",
    "employment_period_type": "",
    "employment_period_years": "",
    "employment_period_months": "",
    "joining_date": "",
    "monthly_salary": "",
    "annual_salary": "",
    "bonus": "",
    "allowances": "",
    "working_hours": "",
    "holidays": "",
    "insurance": "",
    "experience_months": "",
    "has_position": false,
    "position_title": "",
    "job_category_primary": "",
    "job_category_others": [],
    "activity_details": "",
    "activity_details_structured": {
      "department": "",
      "role": "",
      "duties": [],
      "simple_labor_risk_terms": []
    }
  }
}
```

## Section Rules

| section | 用途 | 分ける理由 |
|---|---|---|
| `case` | 申請種別、対象在留資格、流入元 | 案件メタデータ |
| `applicant` | 申請人本人と本人に紐づく情報 | 同じ人に属する情報を集約し、top-levelを増やさない |
| `entry_plan` | 主たる活動内容、入国目的、入国予定日、上陸予定港、滞在予定期間、査証申請予定地 | 今回の申請・入国計画であり、申請人本人の属性ではない |
| `employer` | 所属機関そのもの | 会社属性。契約条件や職務内容とは分ける |
| `employment` | 契約形態、就労期間、給与、役職、職種、活動内容詳細 | 今回その会社でどう働くか |
| `proxy` | 代理人 | MVPでは勤務先会社情報を代理人欄の初期値として扱う。将来、人名の代理人担当者を分ける場合は `proxy.*` を明示保存する |
| `intermediary` | 取次者 | 太田さん側の申請アカウントを持つ申請会社情報。固定設定値であり、Gemini抽出対象ではない |
| `receiving_method` | 受領方法 | 初期MVPでは非表示でもよい |

### entry_plan の注意

RASENSには似た名前の項目が3つありますが、canonical path は分けます。

```text
entry_plan.main_activity_category  # 申請概要の「主たる活動内容」
entry_plan.purpose_of_entry        # 身分事項 No.11 の「入国目的」
employment.activity_details        # 所属機関 No.11 の「活動内容詳細」
```

`main_activity_category` と `purpose_of_entry` はどちらも技人国MVPでは固定値候補ですが、RASENS上は別selectです。`activity_details` は職務内容の自由記述であり、これらのselectとは別物です。

### applicant に入れるもの

`passport`, `immigration_history`, `family`, `education`, `employment_history`, `qualifications` は申請人本人に紐づく情報なので `applicant` 配下に置きます。

```text
applicant.passport.number
applicant.immigration_history.criminal_record
applicant.family.has_accompanying_members
applicant.family.has_japan_relatives_or_cohabitants
applicant.family.japan_relatives_or_cohabitants[0].relationship
applicant.family.japan_relatives_or_cohabitants[0].name
applicant.family.japan_relatives_or_cohabitants[0].birth_date
applicant.family.japan_relatives_or_cohabitants[0].nationality_region
applicant.family.japan_relatives_or_cohabitants[0].will_cohabit
applicant.family.japan_relatives_or_cohabitants[0].workplace_or_school_name
applicant.family.japan_relatives_or_cohabitants[0].residence_card_or_certificate_number
applicant.education[0].school_name
applicant.has_employment_history
applicant.employment_history[0].country_region
applicant.employment_history[0].start_month_unknown
applicant.employment_history[0].start_date
applicant.employment_history[0].end_month_unknown
applicant.employment_history[0].end_date
applicant.employment_history[0].company_name_en
applicant.employment_history[0].company_name_local
applicant.qualifications.it.has_qualification
```

在日親族・同居者と職歴は、RASENS上は複数枠があります。MVPでは最大3件までをUIとmappingで扱い、4件以上は要確認として人がRASENS側で追加入力します。情報がない場合は boolean を `false`、明細配列を空にし、空の3枠をFirestoreに常時保存しません。

### employer と employment は分ける

`employer` は会社そのものです。契約形態や給与を入れません。

`employment` は申請人と所属機関の今回の関係です。`contract.contract_type` のような単独sectionは作らず、`employment.contract_type` に統一します。

```text
employer.name
employer.corporate_number
employer.address

employment.contract_type
employment.job_title
employment.work_location
employment.monthly_salary
employment.job_category_primary
employment.activity_details
```

### proxy と intermediary

`proxy` は在留資格認定証明書交付申請における代理人欄です。MVPでは勤務先会社情報を代理人欄の初期値として扱い、`proxy.name`, `proxy.postal_code`, `proxy.address`, `proxy.phone` を `employer.*` から生成します。人名の代理人担当者を分ける運用に変える場合は、企業マスターまたはケース入力で `proxy.*` を明示保存します。

`intermediary` は取次者です。案件書類から抽出するものではなく、太田さん側の申請アカウントを持つ申請会社情報を固定設定値として使います。通常は `case_data` に保存せず、`application_data.rows` 生成時に設定から注入します。投入時点の再現性が必要な場合だけ、設定値のsnapshotを `case_data.intermediary.*` にコピーします。

## required の扱い

`required` は1種類にまとめません。混ぜると、Gemini抽出失敗、RASENS投入前警告、業務上の不足確認が区別できなくなります。

| 種類 | 保存・管理場所 | 用途 |
|---|---|---|
| schema required | `canonical_case_data_v2.md` / backend・frontend型 | `case_data` の構造を保つための最小必須項目 |
| RASENS required | `rasens_offer_fields.json` / mapping検証 | RASENS画面上の必須表示・入力制約 |
| review required | `review.missing_items`, `review.validation_errors` | 業務上、人が確認すべき不足・矛盾 |

たとえば取次者はRASENS上必須になりえますが、固定設定値なのでGemini抽出requiredではありません。旅券番号はフォーム上のrequiredだけでは判断せず、業務レビュー側で不足確認します。

## 命名ルール

| 方針 | 例 |
|---|---|
| top-level section は増やしすぎない | `passport` top-level ではなく `applicant.passport` |
| RASENSの意味に近い英語名を使う | `nationality_region`, `birth_date`, `sex` |
| 複合項目は意味単位でネストする | `applicant.japan_contact.address` |
| 繰り返し項目は配列で持つ | `applicant.education[]`, `applicant.employment_history[]` |
| 画面ID/nameは入れない | `field_id`, `field_name`, `item[187].textData` は禁止 |
| 不明と非該当を区別する | 未回収は空/null、非該当は明示的な false や `not_applicable` |

## field_metadata

`field_metadata` は canonical dot path をキーにします。`case_data` の中には入れません。

```json
{
  "applicant.birth_date": {
    "source_refs": [
      {
        "document_id": "doc_passport",
        "page": 1,
        "text_quote": "01 JAN 1998",
        "confidence": 0.92,
        "bbox": { "y_min": 100, "x_min": 120, "y_max": 140, "x_max": 300 }
      }
    ],
    "human_reviewed": false,
    "human_edited": false,
    "original_value": "1998-01-01"
  },
  "applicant.passport.expiry_date": {
    "source_refs": [],
    "human_reviewed": false,
    "human_edited": false,
    "original_value": ""
  }
}
```

| field | 役割 |
|---|---|
| `source_refs` | 参照元書類、ページ、引用、信頼度 |
| `human_reviewed` | 人が確認済みか |
| `human_edited` | 人が修正したか |
| `original_value` | 人手修正前の値 |

Gemini schema では state数制限を避けるために `{ value, source }` の短い形式を使ってもよいですが、Firestore保存前に上記へ正規化します。

## review

`review` は frontend が扱いやすい object array に統一します。Gemini raw が string array を返す場合は保存前に変換します。

```json
{
  "schema_version": "2.0",
  "case_id": "case_xxx",
  "expected_route": "needs_review",
  "missing_documents": [
    {
      "path": "supporting_documents.graduation_certificate",
      "reason": "卒業証明書が見つからない"
    }
  ],
  "missing_items": [
    {
      "path": "applicant.sex",
      "reason": "提出資料から性別を確認できない"
    }
  ],
  "validation_errors": [
    {
      "path": "applicant.passport.expiry_date",
      "reason": "入国予定日より前に旅券期限が切れる"
    }
  ],
  "findings": [
    {
      "code": "duties_education_link_weak",
      "severity": "medium",
      "message": "職務内容と専攻のつながりが弱い可能性がある"
    }
  ]
}
```

## Gemini raw の扱い

Gemini raw output は正本ではありません。必要な場合のみ、デバッグ・評価用に `extraction.raw_case_data` または別collectionの `extraction_runs/{run_id}` に保存します。

通常の画面・APIは次だけを読みます。

- `case_data`
- `field_metadata`
- `review`
- `document_manifest`

## 旧pathからcanonical pathへの移行

| legacy path | canonical path |
|---|---|
| `applicant.nationality` | `applicant.nationality_region` |
| `applicant.date_of_birth` | `applicant.birth_date` |
| `applicant.gender` | `applicant.sex` |
| `applicant.place_of_birth` | `applicant.birth_place` |
| `passport.number` | `applicant.passport.number` |
| `passport.expiry_date` | `applicant.passport.expiry_date` |
| `applicant.japan_postal_code` | `applicant.japan_contact.postal_code` |
| `applicant.japan_address` | `applicant.japan_contact.address` |
| `applicant.japan_phone` | `applicant.japan_contact.phone` |
| `applicant.japan_mobile` | `applicant.japan_contact.mobile` |
| `applicant.email` | `applicant.japan_contact.email` |
| `application.desired_status_label` | `entry_plan.main_activity_category` |
| `application.purpose_of_entry` | `entry_plan.purpose_of_entry` |
| `application.planned_entry_date` | `entry_plan.planned_entry_date` |
| `application.planned_port` | `entry_plan.planned_port` |
| `application.planned_port_other` | `entry_plan.planned_port_other` |
| `application.planned_period_years` | `entry_plan.planned_period_years` |
| `application.planned_period_months` | `entry_plan.planned_period_months` |
| `application.visa_application_location` | `entry_plan.visa_application_location` |
| `application.has_accompanying` | `applicant.family.has_accompanying_members` |
| `family.has_accompanying_members` | `applicant.family.has_accompanying_members` |
| `family.has_japan_relatives_or_cohabitants` | `applicant.family.has_japan_relatives_or_cohabitants` |
| `family.japan_relatives_or_cohabitants[]` | `applicant.family.japan_relatives_or_cohabitants[]` |
| `immigration_history.has_entries` | `applicant.immigration_history.has_entries` |
| `immigration_history.entries_count` | `applicant.immigration_history.entries_count` |
| `immigration_history.has_criminal_record` | `applicant.immigration_history.criminal_record` |
| `immigration_history.criminal_record` | `applicant.immigration_history.criminal_record` |
| `immigration_history.latest_entry_start` | `applicant.immigration_history.latest_entry.start_date` |
| `immigration_history.latest_entry_end` | `applicant.immigration_history.latest_entry.end_date` |
| `immigration_history.prior_coe_applications.has_history` | `applicant.immigration_history.prior_coe_applications.has_history` |
| `immigration_history.prior_coe_applications.count` | `applicant.immigration_history.prior_coe_applications.count` |
| `immigration_history.prior_coe_applications.denial_count` | `applicant.immigration_history.prior_coe_applications.denial_count` |
| `immigration_history.deportation_or_departure_order` | `applicant.immigration_history.deportation_or_departure_order` |
| `immigration_history.deportation_count` | `applicant.immigration_history.deportation_count` |
| `immigration_history.deportation_latest_date` | `applicant.immigration_history.deportation_latest_date` |
| `education[0].school_name` | `applicant.education[0].school_name` |
| `education[0].level` | `applicant.education[0].level` |
| `education[0].level_detail` | `applicant.education[0].level_detail` |
| `education[0].level_other` | `applicant.education[0].level_other` |
| `education[0].graduation_date` | `applicant.education[0].graduation_date` |
| `major.field` | `applicant.education[0].major_field` |
| `major.field_other` | `applicant.education[0].major_field_other` |
| `it_qualification.has_qualification` | `applicant.qualifications.it.has_qualification` |
| `it_qualification.qualification_name` | `applicant.qualifications.it.qualification_name` |
| `employment_history[]` | `applicant.employment_history[]` |
| `contract.contract_type` | `employment.contract_type` |
| `employment_conditions.employment_period_type` | `employment.employment_period_type` |
| `employment_conditions.employment_period_years` | `employment.employment_period_years` |
| `employment_conditions.employment_period_months` | `employment.employment_period_months` |
| `employment_conditions.joining_date` | `employment.joining_date` |
| `employment_conditions.monthly_salary` | `employment.monthly_salary` |
| `employment_conditions.job_title` | `employment.job_title` |
| `employment_conditions.work_location` | `employment.work_location` |
| `employment_conditions.annual_salary` | `employment.annual_salary` |
| `employment_conditions.bonus` | `employment.bonus` |
| `employment_conditions.allowances` | `employment.allowances` |
| `employment_conditions.working_hours` | `employment.working_hours` |
| `employment_conditions.holidays` | `employment.holidays` |
| `employment_conditions.insurance` | `employment.insurance` |
| `employment_conditions.experience_months` | `employment.experience_months` |
| `employment_conditions.has_position` | `employment.has_position` |
| `employment_conditions.position_title` | `employment.position_title` |
| `employment_conditions.job_category_primary` | `employment.job_category_primary` |
| `activity_details.description` | `employment.activity_details` |
| `application.activity_details` | `employment.activity_details` |
| `employer.employment_insurance_no` | `employer.employment_insurance_office_number` |

Firestore既存データは本番利用前なので、migrationを厚く作らず削除・再抽出でよいです。
