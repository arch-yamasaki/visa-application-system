import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { apiClient } from '../api/client'
import FieldPanel from '../components/review/FieldPanel'
import DocumentViewer from '../components/viewer/DocumentViewer'
import ReviewBanner from '../components/review/ReviewBanner'
import type { CaseDocument } from '../types/caseData'
import { useViewerStore } from '../store/viewerStore'

export default function ReviewPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const [caseDoc, setCaseDoc] = useState<CaseDocument | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const setDocuments = useViewerStore((s) => s.setDocuments)

  useEffect(() => {
    if (!caseId) return
    apiClient.getCase(caseId).then((doc) => {
      setCaseDoc(doc)
      if (doc.document_manifest?.documents) {
        setDocuments(doc.document_manifest.documents)
      }
    }).finally(() => setLoading(false))
  }, [caseId, setDocuments])

  const handleFieldUpdate = (fieldPath: string, value: string) => {
    if (!caseDoc) return
    setCaseDoc((prev) => {
      if (!prev) return prev
      const updated = { ...prev }
      // Update the value in case_data using dot-path
      const parts = fieldPath.split('.')
      let obj: Record<string, unknown> = { ...updated.case_data } as unknown as Record<string, unknown>
      updated.case_data = obj as unknown as CaseDocument['case_data']
      for (let i = 0; i < parts.length - 1; i++) {
        const next = { ...(obj[parts[i]] as Record<string, unknown>) }
        obj[parts[i]] = next
        obj = next
      }
      obj[parts[parts.length - 1]] = value

      // Mark as human-edited in field_metadata
      const fm = { ...updated.field_metadata }
      fm[fieldPath] = {
        ...fm[fieldPath],
        human_reviewed: true,
        human_edited: true,
      }
      updated.field_metadata = fm
      return updated
    })
  }

  const handleConfirm = async () => {
    if (!caseId || !caseDoc) return
    setSaving(true)
    try {
      await apiClient.updateCase(caseId, {
        case_data: caseDoc.case_data,
        field_metadata: caseDoc.field_metadata,
        workflow_state: 'ready_to_fill',
      })
      setCaseDoc((prev) => prev ? { ...prev, workflow_state: 'ready_to_fill' } : prev)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="p-6 text-gray-500">Loading case...</div>
  }

  if (!caseDoc) {
    return <div className="p-6 text-red-500">Case not found</div>
  }

  return (
    <div className="flex flex-col h-[calc(100vh-52px)]">
      <ReviewBanner
        caseId={caseDoc.case_id}
        workflowState={caseDoc.workflow_state}
        fieldMetadata={caseDoc.field_metadata}
        review={caseDoc.review}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Field Panel */}
        <div className="w-1/2 border-r border-gray-200 overflow-y-auto">
          <FieldPanel
            caseData={caseDoc.case_data}
            fieldMetadata={caseDoc.field_metadata}
            review={caseDoc.review}
            onFieldUpdate={handleFieldUpdate}
          />
        </div>

        {/* Right: Document Viewer */}
        <div className="w-1/2 overflow-hidden">
          <DocumentViewer caseId={caseDoc.case_id} />
        </div>
      </div>

      {/* Bottom: Confirm Bar */}
      <div className="border-t border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
        <span className="text-sm text-gray-500">
          {caseDoc.workflow_state === 'ready_to_fill'
            ? 'Confirmed and ready for form fill'
            : 'Review all fields before confirming'}
        </span>
        <button
          onClick={handleConfirm}
          disabled={saving || caseDoc.workflow_state === 'ready_to_fill'}
          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium"
        >
          {saving ? 'Saving...' : caseDoc.workflow_state === 'ready_to_fill' ? 'Confirmed' : 'Confirm & Complete'}
        </button>
      </div>
    </div>
  )
}
