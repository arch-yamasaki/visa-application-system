import { useEffect, useState, useCallback } from 'react'
import { useViewerStore } from '../../store/viewerStore'
import { apiClient } from '../../api/client'
import PdfViewer from './PdfViewer'
import ImageViewer from './ImageViewer'
import HtmlViewer from './HtmlViewer'

interface Props {
  caseId: string
}

export default function DocumentViewer({ caseId }: Props) {
  const documents = useViewerStore((s) => s.documents)
  const currentDocumentId = useViewerStore((s) => s.currentDocumentId)
  const currentPage = useViewerStore((s) => s.currentPage)
  const highlightSourceRef = useViewerStore((s) => s.highlightSourceRef)
  const selectDocument = useViewerStore((s) => s.selectDocument)

  const [documentUrl, setDocumentUrl] = useState<string | null>(null)
  const [sheets, setSheets] = useState<string[]>([])
  const [selectedSheet, setSelectedSheet] = useState<string | undefined>()

  const currentDoc = documents.find((d) => d.document_id === currentDocumentId)

  const ext = currentDoc?.file_name?.split('.').pop()?.toLowerCase()
  const isOfficeDoc = ['docx', 'xlsx'].includes(ext ?? '')
  const isXlsx = ext === 'xlsx'
  const isPdf = ext === 'pdf'
  const isImage = ['png', 'jpg', 'jpeg'].includes(ext ?? '')

  // PDF/画像は認証必須の /content から blob で取得し、objectURL で viewer に渡す
  // (office docs は preview API を HtmlViewer 側で認証付き取得する)
  useEffect(() => {
    setDocumentUrl(null)
    if (!currentDocumentId || isOfficeDoc) return

    let objectUrl: string | null = null
    let cancelled = false
    apiClient.getDocumentBlobUrl(caseId, currentDocumentId).then((url) => {
      if (cancelled) {
        URL.revokeObjectURL(url)
        return
      }
      objectUrl = url
      setDocumentUrl(url)
    })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [caseId, currentDocumentId, isOfficeDoc])

  // Fetch sheet names for xlsx
  useEffect(() => {
    if (!currentDocumentId || !isXlsx) {
      setSheets([])
      setSelectedSheet(undefined)
      return
    }
    apiClient.getDocumentSheets(caseId, currentDocumentId).then((r) => {
      setSheets(r.sheets)
      setSelectedSheet(undefined) // 全シート表示（デフォルト）
    }).catch(() => {
      setSheets([])
    })
  }, [caseId, currentDocumentId, isXlsx])

  const handleSheetChange = useCallback((sheet: string) => {
    setSelectedSheet(sheet)
  }, [])

  const previewUrl = isOfficeDoc && currentDocumentId
    ? apiClient.getDocumentPreviewUrl(caseId, currentDocumentId, selectedSheet)
    : null
  const url = previewUrl ?? documentUrl

  if (documents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        書類がアップロードされていません
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Document tabs */}
      <div className="flex border-b border-gray-200 bg-gray-50 overflow-x-auto">
        {documents.map((doc) => (
          <button
            key={doc.document_id}
            onClick={() => selectDocument(doc.document_id)}
            className={`px-3 py-2 text-xs whitespace-nowrap border-b-2 transition-colors ${
              doc.document_id === currentDocumentId
                ? 'border-blue-500 text-blue-700 bg-white'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {doc.file_name}
          </button>
        ))}
      </div>

      {/* Viewer area */}
      <div className="flex-1 overflow-auto bg-gray-100">
        {!url ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            書類を読み込み中...
          </div>
        ) : isPdf ? (
          <PdfViewer url={url} page={currentPage} sourceRef={highlightSourceRef} />
        ) : isImage ? (
          <ImageViewer url={url} />
        ) : isOfficeDoc ? (
          <HtmlViewer
            url={url}
            sourceRef={highlightSourceRef}
            sheets={isXlsx ? sheets : undefined}
            onSheetChange={isXlsx ? handleSheetChange : undefined}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            未対応のファイル形式: .{ext}
          </div>
        )}
      </div>
    </div>
  )
}
