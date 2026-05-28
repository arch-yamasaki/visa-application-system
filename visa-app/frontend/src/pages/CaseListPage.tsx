import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiClient } from '../api/client'
import CopyableCaseId from '../components/common/CopyableCaseId'
import { getDisplayValue } from '../lib/fieldPaths'
import { isExtractedWorkflowState, toWorkflowDisplayState, workflowStateColor, workflowStateLabel } from '../lib/workflowState'
import type { CaseSummary } from '../types/caseData'

export default function CaseListPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.listCases().then(setCases).finally(() => setLoading(false))
  }, [])

  const handleCreate = async () => {
    const created = await apiClient.createCase({
      application_type: 'certificate_of_eligibility',
      target_status: 'engineer_humanities_international',
    })
    navigate(`/cases/${created.case_id}/upload${location.search}`)
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-gray-800">案件一覧</h2>
        <button
          onClick={handleCreate}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          + 新規案件
        </button>
      </div>

      {loading ? (
        <p className="text-gray-500">読込中...</p>
      ) : cases.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg mb-2">案件がありません</p>
          <p className="text-sm">新規案件を作成してください</p>
        </div>
      ) : (
        <div className="space-y-2">
          {cases.map((c) => (
            <div
              key={c.case_id}
              onClick={() => {
                const dest = isExtractedWorkflowState(c.workflow_state)
                  ? `/cases/${c.case_id}/review`
                  : `/cases/${c.case_id}/upload`
                navigate(`${dest}${location.search}`)
              }}
              className="flex items-center justify-between p-4 bg-white rounded-lg border border-gray-200 hover:border-blue-300 cursor-pointer transition-colors"
            >
              <div className="min-w-0">
                <p className="font-medium text-gray-800 text-sm truncate">
                  {c.display_name || c.applicant_name_preview || c.case_id}
                </p>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                  {c.applicant_name && <span>申請人: {c.applicant_name}</span>}
                  {c.employer_name && <span>所属機関: {c.employer_name}</span>}
                  {c.target_status && <span>在留資格: {getDisplayValue(c.target_status)}</span>}
                </div>
                <CopyableCaseId
                  caseId={c.case_id}
                  className="mt-1 text-xs text-gray-400"
                  stopPropagation
                />
              </div>
              <span className={`ml-4 shrink-0 px-2 py-0.5 rounded text-xs font-medium ${workflowStateColor[toWorkflowDisplayState(c.workflow_state)]}`}>
                {workflowStateLabel[toWorkflowDisplayState(c.workflow_state)]}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
