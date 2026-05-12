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
      await apiClient.startExtraction(caseId)
      // Poll for completion
      const poll = setInterval(async () => {
        const status = await apiClient.getExtractionStatus(caseId)
        setExtractionStatus(status.status)
        if (status.status === 'completed' || status.status === 'needs_review') {
          clearInterval(poll)
          setExtracting(false)
          navigate(`/cases/${caseId}/review`)
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
        Upload Documents
      </h2>
      <p className="text-sm text-gray-500 mb-6">
        Case: <span className="font-mono">{caseId}</span>
      </p>

      <DropZone onFilesSelected={handleFilesSelected} disabled={uploading || extracting} />

      {uploading && (
        <p className="text-sm text-blue-600 mt-3">Uploading...</p>
      )}

      <FileList documents={documents} />

      <div className="mt-6 flex items-center gap-4">
        <button
          onClick={handleExtract}
          disabled={extracting || documents.length === 0}
          className="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium"
        >
          {extracting ? 'Extracting...' : 'Start Extraction'}
        </button>
        {documents.length > 0 && !extracting && (
          <button
            onClick={() => navigate(`/cases/${caseId}/review`)}
            className="px-4 py-2 text-gray-600 hover:text-gray-800 text-sm"
          >
            Skip to Review
          </button>
        )}
      </div>

      {extracting && <ExtractionProgress status={extractionStatus} />}
    </div>
  )
}
