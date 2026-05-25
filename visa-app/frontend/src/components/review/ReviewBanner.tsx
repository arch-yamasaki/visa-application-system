import CopyableCaseId from '../common/CopyableCaseId'
import { toWorkflowDisplayState, workflowStateColor, workflowStateLabel } from '../../lib/workflowState'

interface Props {
  caseId: string
  workflowState: string
}

export default function ReviewBanner({ caseId, workflowState }: Props) {
  const displayState = toWorkflowDisplayState(workflowState)

  return (
    <div className="bg-white border-b border-gray-200">
      <div className="px-6 py-2.5 flex items-center gap-5 text-sm">
        <CopyableCaseId
          caseId={caseId}
          className="text-gray-500 text-xs"
          feedbackClassName="text-xs"
        />
        <span className={`px-2 py-0.5 rounded text-xs font-medium ${workflowStateColor[displayState]}`}>
          {workflowStateLabel[displayState]}
        </span>
        {displayState === 'extracted' && (
          <span className="text-xs text-gray-500">抽出結果を確認・編集できます</span>
        )}
      </div>
    </div>
  )
}
