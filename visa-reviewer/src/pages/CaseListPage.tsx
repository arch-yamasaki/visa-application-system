import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../api/client'
import type { CaseSummary } from '../types/caseData'

export default function CaseListPage() {
  const navigate = useNavigate()
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
    navigate(`/cases/${created.case_id}/upload`)
  }

  const stateLabel: Record<string, string> = {
    draft: '下書き',
    uploading: 'アップロード中',
    extracting: '抽出中...',
    needs_review: '要レビュー',
    ready_to_fill: '入力準備完了',
    archived: 'アーカイブ',
  }

  const stateColor: Record<string, string> = {
    draft: 'bg-gray-100 text-gray-600',
    uploading: 'bg-blue-100 text-blue-700',
    extracting: 'bg-yellow-100 text-yellow-700',
    needs_review: 'bg-orange-100 text-orange-700',
    ready_to_fill: 'bg-green-100 text-green-700',
    archived: 'bg-gray-100 text-gray-400',
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
                const dest = c.workflow_state === 'draft' || c.workflow_state === 'uploading'
                  ? `/cases/${c.case_id}/upload`
                  : `/cases/${c.case_id}/review`
                navigate(dest)
              }}
              className="flex items-center justify-between p-4 bg-white rounded-lg border border-gray-200 hover:border-blue-300 cursor-pointer transition-colors"
            >
              <div>
                <p className="font-medium text-gray-800 text-sm font-mono">
                  {c.case_id}
                </p>
                {c.applicant_name_preview && (
                  <p className="text-sm text-gray-500 mt-0.5">
                    {c.applicant_name_preview}
                  </p>
                )}
              </div>
              <span
                className={`px-2 py-0.5 rounded text-xs font-medium ${stateColor[c.workflow_state] || 'bg-gray-100 text-gray-600'}`}
              >
                {stateLabel[c.workflow_state] || c.workflow_state}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
