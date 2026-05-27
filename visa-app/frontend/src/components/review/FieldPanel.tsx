import type { CaseData, FieldMetadataMap, Review } from '../../types/caseData'
import FieldSection from './FieldSection'
import FieldRow from './FieldRow'
import RepeatedFieldGroup from './RepeatedFieldGroup'
import {
  flattenCaseData,
  getByPath,
  getFieldInput,
  getFieldLabel,
  getSectionForPath,
  REVIEW_FIELD_PATHS,
  SECTION_ORDER,
} from '../../lib/fieldPaths'
import { getReviewFieldOrder } from '../../lib/reviewFieldOrder'

interface Props {
  caseData: CaseData
  fieldMetadata: FieldMetadataMap
  review: Review
  onFieldUpdate: (fieldPath: string, value: string) => void
}

const REPEATED_FIELD_PREFIXES = [
  'applicant.family.japan_relatives_or_cohabitants.',
  'applicant.employment_history.',
]

const JAPAN_RELATIVE_FIELDS = [
  { path: 'relationship' },
  { path: 'name' },
  { path: 'birth_date' },
  { path: 'nationality_region' },
  { path: 'will_cohabit' },
  { path: 'workplace_or_school_name' },
  { path: 'residence_card_or_certificate_number' },
]

const EMPLOYMENT_HISTORY_FIELDS = [
  { path: 'country_region' },
  { path: 'start_month_unknown' },
  { path: 'start_date' },
  { path: 'end_month_unknown' },
  { path: 'end_date' },
  { path: 'company_name_en' },
  { path: 'company_name_local' },
]

function isRepeatedDetailPath(path: string): boolean {
  return REPEATED_FIELD_PREFIXES.some((prefix) => path.startsWith(prefix))
}

function isTruthy(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value === 1
  if (typeof value === 'string') {
    return ['true', 'yes', '有', 'あり', '有 yes', '1'].includes(value.trim().toLowerCase())
  }
  return false
}

function issuePath(item: unknown): string | null {
  if (typeof item === 'object' && item !== null && 'path' in item) {
    const path = (item as { path?: unknown }).path
    return typeof path === 'string' && path ? path : null
  }
  if (typeof item === 'string' && item.includes('.') && !/\s/.test(item)) {
    return item
  }
  return null
}

export default function FieldPanel({ caseData, fieldMetadata, review, onFieldUpdate }: Props) {
  const fields = flattenCaseData(caseData).filter(
    (field) => field.path !== 'case.workflow_state' && !isRepeatedDetailPath(field.path),
  )

  // Build set of flagged paths
  const missingPaths = new Set(
    review.missing_items?.map(issuePath).filter((path): path is string => Boolean(path)) ?? [],
  )
  const errorPaths = new Set(
    review.validation_errors?.map(issuePath).filter((path): path is string => Boolean(path)) ?? [],
  )
  const visibleFields = [...fields]
  const existingPaths = new Set(visibleFields.map((field) => field.path))
  for (const path of REVIEW_FIELD_PATHS) {
    if (!existingPaths.has(path)) {
      visibleFields.push({ path, value: getByPath(caseData, path) })
      existingPaths.add(path)
    }
  }
  for (const path of [...missingPaths, ...errorPaths]) {
    if (!existingPaths.has(path)) {
      visibleFields.push({ path, value: undefined })
      existingPaths.add(path)
    }
  }

  // Group by section
  const sections = new Map<string, { path: string; value: unknown }[]>()
  for (const field of visibleFields) {
    const section = getSectionForPath(field.path)
    if (!sections.has(section)) sections.set(section, [])
    sections.get(section)!.push(field)
  }
  for (const sectionFields of sections.values()) {
    sectionFields.sort((a, b) => (
      getReviewFieldOrder(a.path) - getReviewFieldOrder(b.path)
      || a.path.localeCompare(b.path)
    ))
  }

  // Sort sections by SECTION_ORDER; unknown sections go to the end
  const sortedSections = Array.from(sections.entries()).sort(([a], [b]) => {
    const ai = (SECTION_ORDER as readonly string[]).indexOf(a)
    const bi = (SECTION_ORDER as readonly string[]).indexOf(b)
    return (ai === -1 ? SECTION_ORDER.length : ai) - (bi === -1 ? SECTION_ORDER.length : bi)
  })

  return (
    <div data-field-panel>
      {sortedSections.map(([section, sectionFields]) => {
        return (
          <FieldSection
            key={section}
            title={section}
            fieldCount={sectionFields.length}
          >
            {sectionFields.map((f) => (
              <div key={f.path}>
                <FieldRow
                  label={getFieldLabel(f.path)}
                  fieldPath={f.path}
                  value={f.value}
                  input={getFieldInput(f.path)}
                  meta={fieldMetadata[f.path]}
                  onUpdate={onFieldUpdate}
                />
                {f.path === 'applicant.family.has_japan_relatives_or_cohabitants' && (
                  <RepeatedFieldGroup
                    title="在日親族・同居者 詳細"
                    itemLabel="親族・同居者"
                    basePath="applicant.family.japan_relatives_or_cohabitants"
                    maxItems={3}
                    fields={JAPAN_RELATIVE_FIELDS}
                    enabled={isTruthy(getByPath(caseData, 'applicant.family.has_japan_relatives_or_cohabitants'))}
                    caseData={caseData}
                    fieldMetadata={fieldMetadata}
                    onFieldUpdate={onFieldUpdate}
                  />
                )}
                {f.path === 'applicant.has_employment_history' && (
                  <RepeatedFieldGroup
                    title="職歴 詳細"
                    itemLabel="職歴"
                    basePath="applicant.employment_history"
                    maxItems={3}
                    fields={EMPLOYMENT_HISTORY_FIELDS}
                    enabled={isTruthy(getByPath(caseData, 'applicant.has_employment_history'))}
                    caseData={caseData}
                    fieldMetadata={fieldMetadata}
                    onFieldUpdate={onFieldUpdate}
                  />
                )}
              </div>
            ))}
          </FieldSection>
        )
      })}
    </div>
  )
}
