/**
 * TypeScript port of rasens-autofill/scripts/build_application_data.py
 *
 * Converts canonical case_data + mapping into Chrome-extension autofill rows.
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyValue = any

interface VisibleCondition {
  path: string
  operator?: string
  value?: AnyValue
}

interface MappingItem {
  canonical_id: string
  value_path: string
  transform?: string
  section?: string
  form_item_no?: string
  label?: string
  field_name?: string
  field_id?: string
  input_type?: string
  visible_when?: VisibleCondition[]
}

interface MappingData {
  mappings: MappingItem[]
}

export interface ApplicationRow {
  section: string
  no: string
  label: string
  field_name: string
  field_id: string
  input_type: string
  display_value: string
  fill_value: string
  source_page: string
  confidence: string
  canonical_id: string
  notes: string
}

/**
 * Navigate a nested object/array by dot-separated path.
 */
export function getByPath(data: AnyValue, dottedPath: string): AnyValue {
  let current: AnyValue = data
  for (const part of dottedPath.split('.')) {
    if (Array.isArray(current)) {
      if (!/^\d+$/.test(part)) return null
      const index = parseInt(part, 10)
      if (index >= current.length) return null
      current = current[index]
    } else if (current !== null && typeof current === 'object') {
      if (!(part in current)) return null
      current = current[part]
    } else {
      return null
    }
  }
  return current
}

function dateDigits(value: AnyValue, digits: number): string {
  const raw = String(value ?? '')
  const found = raw.match(/\d+/g)
  if (!found) return ''
  return found.join('').slice(0, digits)
}

/**
 * Apply a named transform to a raw value.
 */
export function transformValue(value: AnyValue, transformType: string): string {
  if (value == null) return ''
  const rawValue = String(value).trim()
  if (['unknown', 'not_applicable', 'n/a', 'na'].includes(rawValue.toLowerCase())) {
    return ''
  }

  switch (transformType) {
    case 'date_yyyymmdd':
      return dateDigits(value, 8)
    case 'date_yyyymm':
      return dateDigits(value, 6)
    case 'boolean_yes_no':
      return value ? '有 Yes' : '無 No'
    case 'marital_yes_no':
      return value === 'married' ? '有 Married' : '無 Single'
    case 'sex_ja': {
      const map: Record<string, string> = { male: '男 Male', female: '女 Female' }
      return map[String(value)] ?? String(value)
    }
    default:
      return String(value)
  }
}

/**
 * Check whether a mapping item is visible given the current case data.
 */
export function isVisible(caseData: AnyValue, item: MappingItem): boolean {
  for (const condition of item.visible_when ?? []) {
    const actual = getByPath(caseData, condition.path)
    const operator = condition.operator ?? '=='
    const expected = condition.value
    if (operator === '==' && actual !== expected) return false
    if (operator === '!=' && actual === expected) return false
  }
  return true
}

/**
 * Build autofill rows from case_data and mapping definitions.
 */
export function buildRows(caseData: AnyValue, mappingData: MappingData): ApplicationRow[] {
  const rows: ApplicationRow[] = []
  for (const item of mappingData.mappings ?? []) {
    if (!isVisible(caseData, item)) continue
    const value = getByPath(caseData, item.value_path)
    const fillValue = transformValue(value, item.transform ?? '')
    if (fillValue === '') continue

    const caseId = getByPath(caseData, 'case.case_id') as string | null
    rows.push({
      section: item.section ?? '',
      no: item.form_item_no ?? '',
      label: item.label ?? item.canonical_id,
      field_name: item.field_name ?? '',
      field_id: item.field_id ?? '',
      input_type: item.input_type ?? 'text',
      display_value: fillValue,
      fill_value: fillValue,
      source_page: 'case_data',
      confidence: caseId && caseId.startsWith('demo-') ? 'demo' : 'generated',
      canonical_id: item.canonical_id,
      notes: 'generated from canonical case_data',
    })
  }
  return rows
}
