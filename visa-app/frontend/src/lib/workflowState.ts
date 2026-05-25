export type WorkflowDisplayState = 'draft' | 'extracting' | 'extracted' | 'failed'

export function toWorkflowDisplayState(workflowState: string): WorkflowDisplayState {
  if (workflowState === 'extracting') return 'extracting'
  if (
    workflowState === 'needs_review' ||
    workflowState === 'ready_to_fill' ||
    workflowState === 'extracted'
  ) {
    return 'extracted'
  }
  if (workflowState === 'extraction_failed' || workflowState === 'launch_failed' || workflowState === 'failed') {
    return 'failed'
  }
  return 'draft'
}

export function isExtractedWorkflowState(workflowState: string): boolean {
  return toWorkflowDisplayState(workflowState) === 'extracted'
}

export const workflowStateLabel: Record<WorkflowDisplayState, string> = {
  draft: '未抽出',
  extracting: '抽出中',
  extracted: '抽出済み',
  failed: '抽出失敗',
}

export const workflowStateColor: Record<WorkflowDisplayState, string> = {
  draft: 'bg-gray-100 text-gray-600',
  extracting: 'bg-yellow-100 text-yellow-700',
  extracted: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
}
