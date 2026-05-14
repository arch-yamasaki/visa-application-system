import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiClient } from '../api/client'
import DropZone from '../components/upload/DropZone'
import FileList from '../components/upload/FileList'
import ExtractionProgress from '../components/upload/ExtractionProgress'
import type { DocumentEntry } from '../types/caseData'

export default function UploadPage() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState<DocumentEntry[]>([])
  const [uploading, setUploading] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [extractionStatus, setExtractionStatus] = useState<string | null>(null)
  const [backend, setBackend] = useState<string>('gemini')
  const [pattern, setPattern] = useState<string>('auto')
  const demoSuffix = sessionStorage.getItem('visa_demo_mode') === 'true' ? '?demo=true' : ''

  useEffect(() => {
    if (!caseId) return
    apiClient.listDocuments(caseId).then((docs) => setDocuments(docs))
  }, [caseId])

  const handleFilesSelected = useCallback(
    async (files: File[]) => {
      if (!caseId) return
      setUploading(true)
      try {
        for (const file of files) {
          const doc = await apiClient.uploadDocument(caseId, file)
          setDocuments((prev) => [...prev, doc])
        }
      } finally {
        setUploading(false)
      }
    },
    [caseId],
  )

  const handleExtract = async () => {
    if (!caseId || documents.length === 0) return
    setExtracting(true)
    setExtractionStatus('starting')
    try {
      const result = await apiClient.startExtraction(caseId, { backend, pattern })
      // Gemini returns synchronously with completed status
      if (result.status === 'completed' || result.status === 'needs_review') {
        setExtracting(false)
        navigate(`/cases/${caseId}/review${demoSuffix}`)
        return
      }
      if (result.status === 'extraction_failed' || result.status === 'launch_failed') {
        setExtracting(false)
        setExtractionStatus('failed')
        return
      }
      // Codex async backend → poll for completion
      const poll = setInterval(async () => {
        const status = await apiClient.getExtractionStatus(caseId)
        setExtractionStatus(status.status)
        if (status.status === 'completed' || status.status === 'needs_review') {
          clearInterval(poll)
          setExtracting(false)
          navigate(`/cases/${caseId}/review${demoSuffix}`)
        } else if (status.status === 'failed') {
          clearInterval(poll)
          setExtracting(false)
        }
      }, 3000)
    } catch {
      setExtracting(false)
      setExtractionStatus('failed')
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h2 className="text-xl font-semibold text-gray-800 mb-1">
        書類アップロード
      </h2>
      <p className="text-sm text-gray-500 mb-6">
        案件: <span className="font-mono">{caseId}</span>
      </p>

      <DropZone onFilesSelected={handleFilesSelected} disabled={uploading || extracting} />

      {uploading && (
        <p className="text-sm text-blue-600 mt-3">アップロード中...</p>
      )}

      <FileList documents={documents} />

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-gray-700">
          抽出エンジン
          <select
            value={backend}
            onChange={(e) => setBackend(e.target.value)}
            disabled={extracting}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm"
          >
            <option value="gemini">Gemini</option>
            <option value="codex">Codex</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          抽出方式
          <select
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            disabled={extracting}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm"
          >
            <option value="auto">自動</option>
            <option value="text_only">テキストのみ</option>
            <option value="pdf_direct">PDF直接</option>
            <option value="text_and_image">テキスト+画像</option>
          </select>
        </label>
        <button
          onClick={handleExtract}
          disabled={extracting || documents.length === 0}
          className="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium"
        >
          {extracting ? '抽出中...' : '抽出開始'}
        </button>
        {documents.length > 0 && !extracting && (
          <button
            onClick={() => navigate(`/cases/${caseId}/review${demoSuffix}`)}
            className="px-4 py-2 text-gray-600 hover:text-gray-800 text-sm"
          >
            レビューへ
          </button>
        )}
      </div>

      {extracting && <ExtractionProgress status={extractionStatus} />}
    </div>
  )
}
