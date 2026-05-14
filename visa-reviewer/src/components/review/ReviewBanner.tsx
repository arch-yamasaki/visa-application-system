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
  const progress = total > 0 ? reviewed / total : 0
  const flaggedCount =
    (review.missing_items?.length ?? 0) +
    (review.validation_errors?.length ?? 0)
  const findingsCount = review.findings?.length ?? 0

  const stateLabel: Record<string, string> = {
    needs_review: '要レビュー',
    ready_to_fill: '入力準備完了',
    extracting: '抽出中...',
    draft: '下書き',
    extraction_failed: '抽出失敗',
    launch_failed: '起動失敗',
  }

  const stateColor: Record<string, string> = {
    needs_review: 'bg-orange-100 text-orange-700',
    ready_to_fill: 'bg-green-100 text-green-700',
    extracting: 'bg-yellow-100 text-yellow-700',
    draft: 'bg-gray-100 text-gray-600',
    extraction_failed: 'bg-red-100 text-red-700',
    launch_failed: 'bg-red-100 text-red-700',
  }

  const progressColor = progress >= 1 ? 'bg-green-500' : progress >= 0.5 ? 'bg-blue-500' : 'bg-orange-400'

  return (
    <div className="bg-white border-b border-gray-200">
      <div className="px-6 py-2.5 flex items-center gap-5 text-sm">
        <span className="font-mono text-gray-500 text-xs">{caseId}</span>
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${stateColor[workflowState] || 'bg-gray-100'}`}>
          {stateLabel[workflowState] || workflowState}
        </span>

        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-gray-500 text-xs shrink-0">
            確認済: <strong className="text-gray-700">{reviewed}</strong>/{total}
          </span>
          <div className="flex-1 max-w-48 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${progressColor}`}
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
          <span className="text-[10px] text-gray-400">
            {progress === 0 ? '未確認' : progress >= 1 ? '完了' : `${Math.round(progress * 100)}%`}
          </span>
        </div>

        {flaggedCount > 0 && (
          <span className="text-orange-600 text-xs flex items-center gap-1">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <path d="M8 1L15 14H1L8 1Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              <path d="M8 6V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <circle cx="8" cy="11.5" r="0.75" fill="currentColor" />
            </svg>
            {flaggedCount}件
          </span>
        )}
        {findingsCount > 0 && (
          <span className="text-red-600 text-xs flex items-center gap-1">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            {findingsCount}件
          </span>
        )}
      </div>
    </div>
  )
}
