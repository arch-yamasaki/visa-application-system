import type { CaseData, FieldMetadataMap, Review } from '../../types/caseData'
import FieldSection from './FieldSection'
import FieldRow from './FieldRow'
import { flattenCaseData, getFieldLabel, getSectionForPath } from '../../lib/fieldPaths'

interface Props {
  caseData: CaseData
  fieldMetadata: FieldMetadataMap
  review: Review
  onFieldUpdate: (fieldPath: string, value: string) => void
  onMarkSectionReviewed?: (paths: string[]) => void
}

export default function FieldPanel({ caseData, fieldMetadata, review, onFieldUpdate, onMarkSectionReviewed }: Props) {
  const fields = flattenCaseData(caseData)

  // Build set of flagged paths
  const missingPaths = new Set(review.missing_items?.map((i) => i.path) ?? [])
  const errorPaths = new Set(review.validation_errors?.map((i) => i.path) ?? [])
  const reviewPaths = new Set(
    review.findings
      ?.filter((f) => f.severity === 'medium' || f.severity === 'high')
      .flatMap((f) => f.evidence_refs ?? []) ?? [],
  )

  // Group by section
  const sections = new Map<string, { path: string; value: unknown }[]>()
  for (const field of fields) {
    const section = getSectionForPath(field.path)
    if (!sections.has(section)) sections.set(section, [])
    sections.get(section)!.push(field)
  }

  const getFlagType = (path: string): 'ok' | 'needs_review' | 'missing' | 'error' | 'edited' => {
    if (fieldMetadata[path]?.human_edited) return 'edited'
    if (errorPaths.has(path)) return 'error'
    if (missingPaths.has(path)) return 'missing'
    if (reviewPaths.has(path)) return 'needs_review'
    return 'ok'
  }

  return (
    <div data-field-panel>
      {Array.from(sections.entries()).map(([section, sectionFields]) => {
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
