import type { CaseData } from '../types/caseData'

/** Flatten a nested CaseData into dot-path entries. */
export function flattenCaseData(
  data: CaseData,
): { path: string; value: unknown }[] {
  const result: { path: string; value: unknown }[] = []

  // Skip these top-level keys (not user-facing fields)
  const skipKeys = new Set(['schema_version', 'field_metadata'])

  function walk(obj: unknown, prefix: string) {
    if (obj === null || obj === undefined) return
    if (Array.isArray(obj)) {
      obj.forEach((item, i) => walk(item, `${prefix}.${i}`))
      return
    }
    if (typeof obj === 'object') {
      for (const [key, val] of Object.entries(obj as Record<string, unknown>)) {
        if (prefix === '' && skipKeys.has(key)) continue
        const path = prefix ? `${prefix}.${key}` : key
        if (val !== null && typeof val === 'object' && !Array.isArray(val)) {
          walk(val, path)
        } else if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object') {
          walk(val, path)
        } else {
          result.push({ path, value: val })
        }
      }
    }
  }

  walk(data, '')
  return result
}

/** Map top-level path segments to human-readable section names. */
const sectionMap: Record<string, string> = {
  case: '案件情報',
  applicant: '申請人',
  application: '申請内容',
  passport: '旅券',
  residence_card: '在留カード',
  immigration_history: '出入国歴',
  family: '家族',
  education: '学歴',
  transcript_subjects: '成績科目',
  employment_history: '職歴',
  qualifications: '資格',
  employer: '所属機関',
  proxy: '代理人',
  intermediary: '取次者',
  receiving_method: '受取方法',
  supporting_documents: '添付書類',
  assessments: '審査結果',
}

export function getSectionForPath(path: string): string {
  const top = path.split('.')[0]
  return sectionMap[top] ?? top
}

/** Convert a dot-path to a human-friendly label. */
const labelOverrides: Record<string, string> = {
  'applicant.name_roman': '氏名（ローマ字）',
  'applicant.name_kanji': '氏名（漢字）',
  'applicant.nationality_region': '国籍・地域',
  'applicant.birth_date': '生年月日',
  'applicant.sex': '性別',
  'applicant.marital_status': '配偶者の有無',
  'applicant.birth_place': '出生地',
  'applicant.occupation': '職業',
  'applicant.home_country_address': '本国住所',
  'applicant.japan_contact.postal_code': '郵便番号',
  'applicant.japan_contact.address': '日本の住所',
  'applicant.japan_contact.phone': '電話番号',
  'applicant.japan_contact.mobile': '携帯番号',
  'applicant.japan_contact.email': 'メール',
  'passport.number': '旅券番号',
  'passport.expiry_date': '旅券有効期限',
  'application.desired_status_label': '希望する在留資格',
  'application.planned_entry_date': '入国予定日',
  'application.planned_port': '入国予定港',
  'application.planned_period_years': '希望期間（年）',
  'application.planned_period_months': '希望期間（月）',
  'application.activity_details': '活動内容詳細',
  'application.purpose_of_entry': '入国目的',
  'application.visa_application_location': '査証申請予定地',
  'employer.name': '所属機関名',
  'employer.corporate_number': '法人番号',
  'employer.employee_count': '従業員数',
  'employer.capital_jpy': '資本金（円）',
  'employer.industry': '業種',
  'employer.address': '所在地',
  'employer.phone': '電話番号',
  'employer.representative_name': '代表者氏名',
  'employer.representative_title': '代表者役職',
  'employer.annual_sales_jpy': '年間売上（円）',
  'employer.branch_office': '事業所',
  'case.case_id': '案件ID',
  'case.application_type': '申請種別',
  'case.target_status': '対象在留資格',
  'case.workflow_state': 'ワークフロー状態',
  'case.intake_channel': '受付経路',
  'case.source_organization': '送出機関',
  'case.routed_to_human_reason': '人的判断理由',
  'residence_card.number': '在留カード番号',
  'residence_card.status': '在留資格',
  'residence_card.expiry_date': '有効期限',
  'immigration_history.has_entries': '入国歴の有無',
  'immigration_history.entries_count': '入国回数',
  'family.has_accompanying_members': '同伴家族の有無',
  'family.has_japan_relatives_or_cohabitants': '在日親族の有無',
}

export function getFieldLabel(path: string): string {
  if (labelOverrides[path]) return labelOverrides[path]
  // Take last segment, replace underscores with spaces, capitalize
  const last = path.split('.').pop() ?? path
  return last.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Get a nested value from an object using dot-path. */
export function getByPath(obj: unknown, path: string): unknown {
  const parts = path.split('.')
  let current: unknown = obj
  for (const part of parts) {
    if (current === null || current === undefined) return undefined
    if (typeof current === 'object') {
      current = (current as Record<string, unknown>)[part]
    } else {
      return undefined
    }
  }
  return current
}
