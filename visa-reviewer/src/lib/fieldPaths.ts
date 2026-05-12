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
  case: 'Case Info',
  applicant: 'Applicant',
  application: 'Application',
  passport: 'Passport',
  residence_card: 'Residence Card',
  immigration_history: 'Immigration History',
  family: 'Family',
  education: 'Education',
  transcript_subjects: 'Transcript Subjects',
  employment_history: 'Employment History',
  qualifications: 'Qualifications',
  employer: 'Employer',
  proxy: 'Proxy',
  intermediary: 'Intermediary',
  receiving_method: 'Receiving Method',
  supporting_documents: 'Supporting Documents',
  assessments: 'Assessments',
}

export function getSectionForPath(path: string): string {
  const top = path.split('.')[0]
  return sectionMap[top] ?? top
}

/** Convert a dot-path to a human-friendly label. */
const labelOverrides: Record<string, string> = {
  'applicant.name_roman': 'Name (Roman)',
  'applicant.name_kanji': 'Name (Kanji)',
  'applicant.nationality_region': 'Nationality/Region',
  'applicant.birth_date': 'Birth Date',
  'applicant.sex': 'Sex',
  'applicant.marital_status': 'Marital Status',
  'applicant.birth_place': 'Birth Place',
  'applicant.occupation': 'Occupation',
  'applicant.home_country_address': 'Home Country Address',
  'applicant.japan_contact.postal_code': 'Postal Code',
  'applicant.japan_contact.address': 'Japan Address',
  'applicant.japan_contact.phone': 'Phone',
  'applicant.japan_contact.mobile': 'Mobile',
  'applicant.japan_contact.email': 'Email',
  'passport.number': 'Passport Number',
  'passport.expiry_date': 'Passport Expiry',
  'application.desired_status_label': 'Desired Status',
  'application.planned_entry_date': 'Planned Entry Date',
  'application.planned_port': 'Planned Port',
  'application.planned_period_years': 'Period (Years)',
  'application.planned_period_months': 'Period (Months)',
  'application.activity_details': 'Activity Details',
  'employer.name': 'Employer Name',
  'employer.corporate_number': 'Corporate Number',
  'employer.employee_count': 'Employee Count',
  'employer.capital_jpy': 'Capital (JPY)',
  'case.case_id': 'Case ID',
  'case.application_type': 'Application Type',
  'case.target_status': 'Target Status',
  'case.workflow_state': 'Workflow State',
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
