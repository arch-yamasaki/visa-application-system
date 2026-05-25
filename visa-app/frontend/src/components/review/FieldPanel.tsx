import type { CaseData, FieldMetadataMap, Review } from '../../types/caseData'
import FieldSection from './FieldSection'
import FieldRow from './FieldRow'
import { flattenCaseData, getFieldLabel, getSectionForPath, SECTION_ORDER } from '../../lib/fieldPaths'

interface Props {
  caseData: CaseData
  fieldMetadata: FieldMetadataMap
  review: Review
  onFieldUpdate: (fieldPath: string, value: string) => void
  onMarkSectionReviewed?: (paths: string[]) => void
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

export default function FieldPanel({ caseData, fieldMetadata, review, onFieldUpdate, onMarkSectionReviewed }: Props) {
  const fields = flattenCaseData(caseData)

  // Build set of flagged paths
  const missingPaths = new Set(
    review.missing_items?.map(issuePath).filter((path): path is string => Boolean(path)) ?? [],
  )
  const errorPaths = new Set(
    review.validation_errors?.map(issuePath).filter((path): path is string => Boolean(path)) ?? [],
  )
  const reviewPaths = new Set(
    review.findings
      ?.filter((f) => f.severity === 'medium' || f.severity === 'high')
      .flatMap((f) => f.evidence_refs ?? []) ?? [],
  )
  const visibleFields = [...fields]
  const existingPaths = new Set(visibleFields.map((field) => field.path))
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

  const getFlagType = (path: string): 'action_needed' | 'edited' | null => {
    if (fieldMetadata[path]?.human_edited) return 'edited'
    if (errorPaths.has(path) || missingPaths.has(path) || reviewPaths.has(path)) return 'action_needed'
    return null
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
        const reviewedCount = sectionFields.filter((f) => fieldMetadata[f.path]?.human_reviewed).length
        return (
          <FieldSection
            key={section}
            title={section}
            fieldCount={sectionFields.length}
            reviewedCount={reviewedCount}
            onMarkAllReviewed={
              onMarkSectionReviewed
                ? () => onMarkSectionReviewed(sectionFields.map((f) => f.path))
                : undefined
            }
          >
            {sectionFields.map((f) => (
              <FieldRow
                key={f.path}
                label={getFieldLabel(f.path)}
                fieldPath={f.path}
                value={f.value}
                meta={fieldMetadata[f.path]}
                flagType={getFlagType(f.path)}
                onUpdate={onFieldUpdate}
              />
            ))}
          </FieldSection>
        )
      })}
    </div>
  )
}
