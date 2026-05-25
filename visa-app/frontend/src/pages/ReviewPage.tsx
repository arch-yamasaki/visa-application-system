import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiClient } from '../api/client'
import FieldPanel from '../components/review/FieldPanel'
import DocumentViewer from '../components/viewer/DocumentViewer'
import ReviewBanner from '../components/review/ReviewBanner'
import type { CaseDocument, FieldMetadataMap } from '../types/caseData'
import { useViewerStore } from '../store/viewerStore'

/** APIが返すリスト形式の field_metadata を Record<string, FieldMeta> に変換 */
function normalizeFieldMetadata(raw: unknown): FieldMetadataMap {
  if (!raw) return {}
  if (!Array.isArray(raw)) return raw as FieldMetadataMap
  const map: FieldMetadataMap = {}
  for (const item of raw) {
    const path = item.field_path ?? item.path
    if (!path) continue
    map[path] = {
      source_refs: (item.source_refs ?? []).map((ref: Record<string, unknown>) => ({
        document_id: ref.doc_id ?? ref.document_id ?? '',
        page: Number(ref.page) || 1,
        text_quote: ref.text_quote ?? '',
        confidence: Number(ref.confidence) || 0,
      })),
      human_reviewed: item.human_reviewed,
      human_edited: item.human_edited,
      original_value: item.original_value,
    }
  }
  return map
}

function setValueAtPath<T>(root: T, path: string, value: unknown): T {
  const parts = path.split('.')
  const clone = Array.isArray(root) ? [...root] : { ...(root as Record<string, unknown>) }
  let current: unknown = clone

  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i]
    const nextPart = parts[i + 1]
    const key = Array.isArray(current) ? Number(part) : part
    const container = current as Record<string, unknown> | unknown[]
    const existing = container[key as keyof typeof container]
    const next = Array.isArray(existing)
      ? [...existing]
      : existing && typeof existing === 'object'
        ? { ...(existing as Record<string, unknown>) }
        : /^\d+$/.test(nextPart)
          ? []
          : {}

    ;(container as Record<string, unknown>)[String(key)] = next
    current = next
  }

  const last = parts[parts.length - 1]
  const key = Array.isArray(current) ? Number(last) : last
  ;(current as Record<string, unknown>)[String(key)] = value
  return clone as T
}

export default function ReviewPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const [caseDoc, setCaseDoc] = useState<CaseDocument | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [splitRatio, setSplitRatio] = useState(0.45)
  const [dragging, setDragging] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const setDocuments = useViewerStore((s) => s.setDocuments)

  useEffect(() => {
    if (!caseId) return
    apiClient.getCase(caseId).then((doc) => {
      doc.field_metadata = normalizeFieldMetadata(doc.field_metadata)
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
      updated.case_data = setValueAtPath(updated.case_data, fieldPath, value)

      const fm = { ...updated.field_metadata }
      fm[fieldPath] = {
        ...fm[fieldPath],
        human_edited: true,
      }
      updated.field_metadata = fm
      return updated
    })
  }

  const handleSave = async () => {
    if (!caseId || !caseDoc) return
    setSaving(true)
    try {
      await apiClient.updateCase(caseId, {
        case_data: caseDoc.case_data,
        field_metadata: caseDoc.field_metadata,
      })
    } finally {
      setSaving(false)
    }
  }

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setDragging(true)
  }, [])

  useEffect(() => {
    if (!dragging) return
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const ratio = (e.clientX - rect.left) / rect.width
      setSplitRatio(Math.max(0.25, Math.min(0.75, ratio)))
    }
    const handleMouseUp = () => setDragging(false)
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [dragging])

  if (loading) {
    return <div className="p-6 text-gray-500">案件を読み込み中...</div>
  }

  if (!caseDoc) {
    return <div className="p-6 text-red-500">案件が見つかりません</div>
  }

  const hasExtractedData = caseDoc.case_data && Object.values(caseDoc.case_data).some(
    (v) => typeof v === 'object' && v !== null && Object.keys(v).length > 0,
  )
  if (!hasExtractedData) {
    return (
      <div className="p-6 text-center">
        <p className="text-orange-600 font-medium">抽出データがありません</p>
        <p className="text-sm text-gray-500 mt-2">アップロード画面で書類を投入し、抽出を実行してください。</p>
        <button
          onClick={() => navigate(`/cases/${caseDoc.case_id}/upload`)}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
        >
          アップロード画面へ
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-52px)]">
      <ReviewBanner
        caseId={caseDoc.case_id}
        workflowState={caseDoc.workflow_state}
      />

      <div ref={containerRef} className="flex flex-1 overflow-hidden relative">
        {/* Left: Field Panel */}
        <div
          className="border-r border-gray-200 overflow-y-auto"
          style={{ width: `${splitRatio * 100}%` }}
        >
          <FieldPanel
            caseData={caseDoc.case_data}
            fieldMetadata={caseDoc.field_metadata}
            review={caseDoc.review}
            onFieldUpdate={handleFieldUpdate}
          />
        </div>

        {/* Drag handle */}
        <div
          className={`w-1 cursor-col-resize hover:bg-blue-300 active:bg-blue-400 transition-colors ${
            dragging ? 'bg-blue-400' : 'bg-gray-200'
          }`}
          onMouseDown={handleMouseDown}
        />

        {/* Right: Document Viewer */}
        <div className="flex-1 overflow-hidden">
          <DocumentViewer caseId={caseDoc.case_id} />
        </div>
      </div>

      {/* Bottom: Save Bar */}
      <div className="border-t border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
        <span className="text-sm text-gray-500">
          編集内容を保存できます
        </span>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium transition-colors"
        >
          {saving ? '保存中...' : '保存'}
        </button>
      </div>
    </div>
  )
}
