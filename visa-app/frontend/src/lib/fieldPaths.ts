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

export const REVIEW_FIELD_PATHS = [
  'applicant.family.has_japan_relatives_or_cohabitants',
  'applicant.education.0.country_type',
  'applicant.education.0.level',
  'applicant.education.0.level_detail',
  'applicant.education.0.level_other',
  'applicant.education.0.school_name',
  'applicant.education.0.graduation_date',
  'applicant.education.0.major_field',
  'applicant.education.0.major_field_other',
  'applicant.has_employment_history',
  'proxy.name',
  'proxy.relationship',
  'proxy.postal_code',
  'proxy.address',
  'proxy.phone',
  'proxy.mobile',
  'settings.intermediary.organization',
  'settings.intermediary.name',
  'settings.intermediary.postal_code',
  'settings.intermediary.address',
  'settings.intermediary.phone',
] as const

const sectionRules: [RegExp, string][] = [
  [/^case\./, '申請概要'],
  [/^applicant\.has_employment_history$/, '申請人に関する情報等'],
  [/^applicant\.(education|employment_history|qualifications)\b/, '申請人に関する情報等'],
  [/^applicant\./, '身分事項'],
  [/^entry_plan\./, '入国計画'],
  [/^employer\./, '所属機関'],
  [/^employment\./, '雇用・活動内容'],
  [/^(proxy|receiving_method)\./, '代理人・受領方法'],
  [/^settings\.intermediary\./, '取次者'],
  [/^(supporting_documents|assessments)\./, '審査'],
]

/** セクションの表示順。定義にないセクションは末尾の「その他」に配置。 */
export const SECTION_ORDER = [
  '申請概要',
  '身分事項',
  '入国計画',
  '申請人に関する情報等',
  '所属機関',
  '雇用・活動内容',
  '代理人・受領方法',
  '取次者',
  '審査',
] as const

export function getSectionForPath(path: string): string {
  return sectionRules.find(([pattern]) => pattern.test(path))?.[1] ?? 'その他'
}

/** Convert a dot-path to a human-friendly label. */
const labelOverrides: Record<string, string> = {
  // 案件情報
  'case.case_id': '案件ID',
  'case.application_type': '申請種別',
  'case.target_status': '対象在留資格',
  'case.workflow_state': 'ワークフロー状態',
  'case.intake_channel': '受付経路',
  'case.source_organization': '送出機関',
  'case.routed_to_human_reason': '人的判断理由',

  // 入国計画
  'entry_plan.main_activity_category': '主たる活動内容',
  'entry_plan.purpose_of_entry': '入国目的',
  'entry_plan.planned_entry_date': '入国予定日',
  'entry_plan.planned_port': '入国予定港',
  'entry_plan.planned_period_years': '希望期間（年）',
  'entry_plan.planned_period_months': '希望期間（月）',
  'entry_plan.visa_application_location': '査証申請予定地',

  // 申請人
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

  // 旅券
  'applicant.passport.number': '旅券番号',
  'applicant.passport.expiry_date': '旅券有効期限',

  // 在留カード
  'applicant.residence_card.number': '在留カード番号',
  'applicant.residence_card.status': '在留資格',
  'applicant.residence_card.expiry_date': '有効期限',

  // 家族
  'applicant.family.has_accompanying_members': '同伴者の有無',
  'applicant.family.has_japan_relatives_or_cohabitants': '在日親族及び同居者 有無',
  'applicant.family.japan_relatives_or_cohabitants': '在日親族・同居者',
  'applicant.family.japan_relatives_or_cohabitants.relationship': '続柄',
  'applicant.family.japan_relatives_or_cohabitants.name': '氏名',
  'applicant.family.japan_relatives_or_cohabitants.birth_date': '生年月日',
  'applicant.family.japan_relatives_or_cohabitants.nationality_region': '国籍・地域',
  'applicant.family.japan_relatives_or_cohabitants.will_cohabit': '同居予定の有無',
  'applicant.family.japan_relatives_or_cohabitants.workplace_or_school_name': '勤務先・通学先',
  'applicant.family.japan_relatives_or_cohabitants.residence_card_or_certificate_number': '在留カード番号等',

  // 出入国歴
  'applicant.immigration_history.has_entries': '過去の出入国歴の有無',
  'applicant.immigration_history.entries_count': '過去の出入国歴 回数',
  'applicant.immigration_history.latest_entry.start_date': '直近入国日',
  'applicant.immigration_history.latest_entry.end_date': '直近出国日',
  'applicant.immigration_history.prior_coe_applications.has_history': '在留資格認定証明書申請歴',
  'applicant.immigration_history.prior_coe_applications.count': '申請回数',
  'applicant.immigration_history.prior_coe_applications.denial_count': '不交付回数',
  'applicant.immigration_history.criminal_record': '犯罪歴の有無',
  'applicant.immigration_history.deportation_or_departure_order': '退去強制・出国命令歴',
  'applicant.immigration_history.deportation_count': '退去強制・出国命令歴 回数',
  'applicant.immigration_history.deportation_latest': '直近の退去強制・出国命令年月日',

  // 学歴（配列項目）
  'applicant.education.id': '学歴ID',
  'applicant.education.country_type': '最終学歴 本邦・外国区分',
  'applicant.education.level': '学歴区分',
  'applicant.education.level_detail': '学歴詳細',
  'applicant.education.level_other': '学歴 その他',
  'applicant.education.school_name': '学校名',
  'applicant.education.major_field': '専攻・専門分野',
  'applicant.education.major_field_other': '専攻・専門分野 その他',
  'applicant.education.graduation_date': '卒業年月日',
  'applicant.education.degree': '学位',

  // 成績科目（配列項目）
  'transcript_subjects.name': '科目名',
  'transcript_subjects.matched_duty': '対応職務',

  // 職歴（配列項目）
  'applicant.has_employment_history': '職歴の有無',
  'applicant.employment_history.id': '職歴ID',
  'applicant.employment_history.country_region': '勤務国・地域',
  'applicant.employment_history.start_month_unknown': '入社月不詳',
  'applicant.employment_history.start_date': '入社年月',
  'applicant.employment_history.end_month_unknown': '退社月不詳',
  'applicant.employment_history.end_date': '退社年月',
  'applicant.employment_history.company_name_en': '会社名（英語）',
  'applicant.employment_history.company_name_local': '会社名（現地語）',
  'applicant.employment_history.duties': '職務内容',

  // 資格（配列項目）
  'applicant.qualifications.type': '資格種別',
  'applicant.qualifications.name': '資格名',
  'applicant.qualifications.level': '取得級・レベル',
  'applicant.qualifications.issue_date': '取得日',
  'applicant.qualifications.it.has_qualification': '情報処理資格の有無',
  'applicant.qualifications.it.qualification_name': '情報処理資格名',

  // 所属機関
  'employer.name': '所属機関名',
  'employer.has_corporate_number': '法人番号の有無',
  'employer.corporate_number': '法人番号',
  'employer.office_name': '事業所名',
  'employer.employment_insurance_office_number': '雇用保険適用事業所番号',
  'employer.industry_primary': '主たる業種',
  'employer.industry_other': '業種 その他',
  'employer.postal_code': '郵便番号',
  'employer.address': '所在地',
  'employer.phone': '電話番号',
  'employer.capital_jpy': '資本金（円）',
  'employer.annual_sales_jpy': '年間売上（円）',
  'employer.employee_count': '従業員数',
  'employer.foreign_employee_count': '外国人従業員数',
  'employer.technical_intern_count': '技能実習生数',
  'employer.category': 'カテゴリー',
  'employer.representative_name': '代表者氏名',
  'employer.representative_title': '代表者役職',
  'employer.industry': '業種',
  'employer.branch_office': '事業所',
  'employer.company_name': '会社名',
  'employer.business_description': '事業内容',
  'employer.head_office_address': '本社所在地',
  'employer.capital': '資本金',

  // 代理人（配列項目含む）
  'proxy.name': '代理人 氏名',
  'proxy.relationship': '申請人との関係',
  'proxy.postal_code': '代理人 郵便番号',
  'proxy.address': '代理人 住所',
  'proxy.phone': '代理人 電話番号',
  'proxy.mobile': '代理人 携帯番号',

  // 取次者
  'settings.intermediary.organization': '取次者 所属機関',
  'settings.intermediary.name': '取次者 氏名',
  'settings.intermediary.postal_code': '取次者 郵便番号',
  'settings.intermediary.address': '取次者 住所',
  'settings.intermediary.phone': '取次者 電話番号',

  // 添付書類（配列項目）
  'supporting_documents.document_type': '書類種別',
  'supporting_documents.status': '受領状況',
  'supporting_documents.source': 'ファイル名',
  'supporting_documents.file_name': 'ファイル名',
  'supporting_documents.notes': '備考',

  // 審査結果（配列項目）
  'assessments.type': '審査種別',
  'assessments.status': '判定結果',
  'assessments.summary': '概要',

  // 雇用・活動内容
  'employment.contract_type': '契約の形態',
  'employment.employment_period_type': '就労予定期間',
  'employment.employment_period_years': '就労予定期間（年）',
  'employment.employment_period_months': '就労予定期間（月）',
  'employment.joining_date': '雇用開始年月日',
  'employment.monthly_salary': '月額給与',
  'employment.experience_months': '実務経験月数',
  'employment.has_position': '役職の有無',
  'employment.position_title': '役職名',
  'employment.job_category_primary': '主たる職種',
  'employment.activity_details': '活動内容詳細',
}

/** Strip numeric array indices from a path for label lookup.
 *  e.g. "education.0.school_name" → "education.school_name" */
function stripIndices(path: string): string {
  return path.replace(/\.\d+\./g, '.').replace(/\.\d+$/, '')
}

/** Common field name fragments → Japanese */
const segmentLabels: Record<string, string> = {
  name: '名称', company_name: '会社名', school_name: '学校名',
  description: '説明', business_description: '事業内容',
  address: '住所', head_office_address: '本社所在地',
  capital: '資本金', salary: '給与', monthly_salary: '月給',
  salary_monthly: '月給', annual_salary: '年収', annual_sales: '年間売上',
  job_title: '職種', work_location: '勤務地', joining_date: '入社予定日',
  contract_period: '契約期間', working_hours: '勤務時間', bonus: '賞与',
  nationality: '国籍', gender: '性別', date_of_birth: '生年月日',
  birthday: '生年月日', place_of_birth: '出生地', hometown_city: '出身地',
  passport_number: '旅券番号', passport_expiration_date: '旅券有効期限',
  degree: '学位', major: '専攻', graduation_date: '卒業年月日',
  has_history: '履歴の有無', count: '回数',
  family_in_japan: '在日親族', employment_history: '職歴', work_history: '職歴',
  qualifications: '資格', activity_details: '活動内容',
  criminal_record: '犯罪歴', past_entry_history: '過去の入国歴',
  past_coe_application_history: '過去のCOE申請歴',
  start_date: '開始日', end_date: '終了日',
  phone: '電話番号', mobile: '携帯番号', email: 'メール',
  postal_code: '郵便番号', relationship: '続柄',
  status: 'ステータス', type: '種別', summary: '概要',
  source: '出典', notes: '備考', id: 'ID',
}

export function getFieldLabel(path: string): string {
  if (labelOverrides[path]) return labelOverrides[path]
  const stripped = stripIndices(path)
  if (labelOverrides[stripped]) return labelOverrides[stripped]
  const last = path.split('.').pop() ?? path
  if (segmentLabels[last]) return segmentLabels[last]
  return last.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Map internal enum values to human-readable Japanese labels. */
const valueLabels: Record<string, string> = {
  // 在留資格
  engineer_humanities_international: '技術・人文知識・国際業務',
  highly_skilled_professional: '高度専門職',
  skilled_labor: '技能',
  specified_skilled_worker: '特定技能',
  student: '留学',
  dependent: '家族滞在',
  spouse_of_japanese: '日本人の配偶者等',
  permanent_resident: '永住者',
  long_term_resident: '定住者',
  intra_company_transferee: '企業内転勤',
  business_manager: '経営・管理',
  entertainer: '興行',

  // 申請種別
  certificate_of_eligibility: '在留資格認定証明書交付申請',
  change_of_status: '在留資格変更許可申請',
  extension_of_stay: '在留期間更新許可申請',

  // ワークフロー
  draft: '未抽出',
  extracting: '抽出中',
  extracted: '抽出済み',
  needs_review: '抽出済み',
  ready_to_fill: '抽出済み',
  failed: '抽出失敗',
  extraction_failed: '抽出失敗',
  launch_failed: '抽出失敗',

  // 性別
  male: '男',
  female: '女',

  // 配偶者
  married: '有',
  unmarried: '無',
  single: '無',

  // 有無
  yes: 'あり',
  no: 'なし',
  none: 'なし',
  true: 'あり',
  false: 'なし',
  '有 Yes': 'あり',
  '無 No': 'なし',
  SINGLE: '無',
  MARRIED: '有',
  YES: 'あり',
  NO: 'なし',
  有: 'あり',
  無: 'なし',
  NEPAL: 'ネパール',

  // 学歴区分
  university: '大学',
  University: '大学',
  Bachelor: '大学',
  '大学院（博士） Doctor': '大学院（博士）',
  '大学院（修士） Master': '大学院（修士）',
  '大学 Bachelor': '大学',
  '本邦 Japan': '本邦',
  '外国 Foreign country': '外国',
  '短期大学 Junior college': '短期大学',
  '専門学校 College of technology': '専門学校',
  '高等学校 Senior high school': '高等学校',
  '中学校 Junior high school': '中学校',
  'その他 Others': 'その他',
  graduate_school: '大学院',
  junior_college: '短期大学',
  vocational_school: '専門学校',
  high_school: '高等学校',
  '雇用 Employment': '雇用',
  '委任 Entrustment': '委任',
  '請負 Service contract': '請負',
  '定めあり Fixed': '定めあり',
  '定めなし Non-Fixed': '定めなし',

  // 書類受領状況
  received: '受領済',
  pending: '未受領',
  not_required: '不要',
}

export function getDisplayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  const str = String(value)
  return valueLabels[str] ?? valueLabels[str.toLowerCase()] ?? str
}

export type FieldInputType = 'text' | 'select' | 'number' | 'date' | 'month'

export interface FieldInput {
  type: FieldInputType
  options?: { value: string; label: string }[]
}

const applicationTypeOptions = [
  { value: 'certificate_of_eligibility', label: '在留資格認定証明書交付申請' },
  { value: 'change_of_status', label: '在留資格変更許可申請' },
  { value: 'extension_of_stay', label: '在留期間更新許可申請' },
]

const targetStatusOptions = [
  { value: 'engineer_humanities_international', label: '技術・人文知識・国際業務' },
  { value: 'highly_skilled_professional', label: '高度専門職' },
  { value: 'intra_company_transferee', label: '企業内転勤' },
  { value: 'skilled_labor', label: '技能' },
  { value: 'specified_skilled_worker', label: '特定技能' },
  { value: 'student', label: '留学' },
  { value: 'dependent', label: '家族滞在' },
  { value: 'spouse_of_japanese', label: '日本人の配偶者等' },
  { value: 'business_manager', label: '経営・管理' },
]

const booleanOptions = [
  { value: 'true', label: 'あり' },
  { value: 'false', label: 'なし' },
]

const sexOptions = [
  { value: 'male', label: '男' },
  { value: 'female', label: '女' },
]

const maritalStatusOptions = [
  { value: 'single', label: '無' },
  { value: 'unmarried', label: '無' },
  { value: 'married', label: '有' },
]

const educationCountryOptions = [
  { value: '外国 Foreign country', label: '外国' },
  { value: '本邦 Japan', label: '本邦' },
]

const educationLevelOptions = [
  { value: '大学院（博士） Doctor', label: '大学院（博士）' },
  { value: '大学院（修士） Master', label: '大学院（修士）' },
  { value: '大学 Bachelor', label: '大学' },
  { value: '短期大学 Junior college', label: '短期大学' },
  { value: '専門学校 College of technology', label: '専門学校' },
  { value: '高等学校 Senior high school', label: '高等学校' },
  { value: '中学校 Junior high school', label: '中学校' },
  { value: 'その他 Others', label: 'その他' },
]

const contractTypeOptions = [
  { value: '雇用 Employment', label: '雇用' },
  { value: '委任 Entrustment', label: '委任' },
  { value: '請負 Service contract', label: '請負' },
  { value: 'その他 Others', label: 'その他' },
]

const employmentPeriodOptions = [
  { value: '定めあり Fixed', label: '定めあり' },
  { value: '定めなし Non-Fixed', label: '定めなし' },
]

const documentStatusOptions = [
  { value: 'received', label: '受領済' },
  { value: 'pending', label: '未受領' },
  { value: 'not_required', label: '不要' },
]

const plannedPortOptions = [
  { value: '成田空港(NRT) Narita International Airport', label: '成田空港(NRT)' },
  { value: '羽田空港(HND) Haneda Airport', label: '羽田空港(HND)' },
  { value: '中部国際空港(NGO) Chubu Centrair International Airport', label: '中部国際空港(NGO)' },
  { value: '関西国際空港(KIX) Kansai International Airport', label: '関西国際空港(KIX)' },
  { value: '新千歳空港(CTS) New Chitose Airport', label: '新千歳空港(CTS)' },
  { value: '広島空港(HIJ) Hiroshima Airport', label: '広島空港(HIJ)' },
  { value: '福岡空港(FUK) Fukuoka Airport', label: '福岡空港(FUK)' },
  { value: 'その他 Others', label: 'その他' },
]

const numberPaths = new Set([
  'entry_plan.planned_period_years',
  'entry_plan.planned_period_months',
  'applicant.immigration_history.entries_count',
  'applicant.immigration_history.prior_coe_applications.count',
  'applicant.immigration_history.prior_coe_applications.denial_count',
  'applicant.immigration_history.deportation_count',
  'employer.capital_jpy',
  'employer.annual_sales_jpy',
  'employer.employee_count',
  'employer.foreign_employee_count',
  'employer.technical_intern_count',
  'employment.employment_period_years',
  'employment.employment_period_months',
  'employment.monthly_salary',
  'employment.experience_months',
])

const datePaths = new Set([
  'entry_plan.planned_entry_date',
  'applicant.birth_date',
  'applicant.passport.expiry_date',
  'applicant.residence_card.expiry_date',
  'applicant.immigration_history.latest_entry.start_date',
  'applicant.immigration_history.latest_entry.end_date',
  'applicant.immigration_history.deportation_latest',
  'applicant.family.japan_relatives_or_cohabitants.birth_date',
  'applicant.qualifications.issue_date',
  'employment.joining_date',
])

const monthPaths = new Set([
  'applicant.education.graduation_date',
  'applicant.employment_history.start_date',
  'applicant.employment_history.end_date',
])

const booleanPaths = new Set([
  'applicant.family.has_accompanying_members',
  'applicant.family.has_japan_relatives_or_cohabitants',
  'applicant.family.japan_relatives_or_cohabitants.will_cohabit',
  'applicant.has_employment_history',
  'applicant.immigration_history.has_entries',
  'applicant.immigration_history.prior_coe_applications.has_history',
  'applicant.immigration_history.criminal_record',
  'applicant.immigration_history.deportation_or_departure_order',
  'applicant.qualifications.it.has_qualification',
  'applicant.employment_history.start_month_unknown',
  'applicant.employment_history.end_month_unknown',
  'employer.has_corporate_number',
  'employment.has_position',
])

export function getFieldInput(path: string): FieldInput {
  const stripped = stripIndices(path)
  if (stripped === 'case.application_type') return { type: 'select', options: applicationTypeOptions }
  if (stripped === 'case.target_status') return { type: 'select', options: targetStatusOptions }
  if (booleanPaths.has(stripped)) return { type: 'select', options: booleanOptions }
  if (stripped === 'applicant.sex') return { type: 'select', options: sexOptions }
  if (stripped === 'applicant.marital_status') return { type: 'select', options: maritalStatusOptions }
  if (stripped === 'applicant.education.country_type') return { type: 'select', options: educationCountryOptions }
  if (stripped === 'applicant.education.level') return { type: 'select', options: educationLevelOptions }
  if (stripped === 'employment.contract_type') return { type: 'select', options: contractTypeOptions }
  if (stripped === 'employment.employment_period_type') return { type: 'select', options: employmentPeriodOptions }
  if (stripped === 'entry_plan.planned_port') return { type: 'select', options: plannedPortOptions }
  if (stripped === 'supporting_documents.status') return { type: 'select', options: documentStatusOptions }
  if (numberPaths.has(stripped)) return { type: 'number' }
  if (datePaths.has(stripped)) return { type: 'date' }
  if (monthPaths.has(stripped)) return { type: 'month' }
  return { type: 'text' }
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
