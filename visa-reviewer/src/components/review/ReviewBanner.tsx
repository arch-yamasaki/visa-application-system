import type { FieldMetadataMap, Review } from '../../types/caseData'

interface Props {
  caseId: string
  workflowState: string
  fieldMetadata: FieldMetadataMap
  review: Review
}

export default function ReviewBanner({ caseId, workflowState, fieldMetadata, review }: Props) {
  const entries = Object.entries(fieldMetadata)
  const reviewed = entries.filter(([, m]) => m.human_reviewed).length
  const total = entries.length
  const flaggedCount =
    (review.missing_items?.length ?? 0) +
    (review.validation_errors?.length ?? 0)
  const findingsCount = review.findings?.length ?? 0

  const stateLabel: Record<string, string> = {
    needs_review: 'Needs Review',
    ready_to_fill: 'Ready to Fill',
    extracting: 'Extracting...',
    draft: 'Draft',
  }

  const stateColor: Record<string, string> = {
    needs_review: 'bg-orange-100 text-orange-700',
    ready_to_fill: 'bg-green-100 text-green-700',
    extracting: 'bg-yellow-100 text-yellow-700',
    draft: 'bg-gray-100 text-gray-600',
  }

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-2.5 flex items-center gap-6 text-sm">
      <span className="font-mono text-gray-500">{caseId}</span>
      <span className={`px-2 py-0.5 rounded text-xs font-medium ${stateColor[workflowState] || 'bg-gray-100'}`}>
        {stateLabel[workflowState] || workflowState}
      </span>
      <span className="text-gray-500">
        Fields: <strong className="text-gray-700">{reviewed}</strong>/{total} reviewed
      </span>
      {flaggedCount > 0 && (
        <span className="text-orange-600">
          {flaggedCount} flagged
        </span>
      )}
      {findingsCount > 0 && (
        <span className="text-red-600">
          {findingsCount} findings
        </span>
      )}
    </div>
  )
}
