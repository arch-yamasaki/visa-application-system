import { useEffect } from 'react'
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
  const highlightText = useViewerStore((s) => s.highlightText)
  const signedUrls = useViewerStore((s) => s.signedUrls)
  const setSignedUrl = useViewerStore((s) => s.setSignedUrl)
  const setCurrentDoc = useViewerStore((s) => s.navigateToSource)

  const currentDoc = documents.find((d) => d.document_id === currentDocumentId)

  const ext = currentDoc?.file_name?.split('.').pop()?.toLowerCase()
  const isOfficeDoc = ['docx', 'xlsx', 'xls', 'doc'].includes(ext ?? '')
  const isPdf = ext === 'pdf'
  const isImage = ['png', 'jpg', 'jpeg', 'tiff', 'tif'].includes(ext ?? '')

  // Fetch signed URL for current document (skip for office docs)
  useEffect(() => {
    if (!currentDocumentId || signedUrls[currentDocumentId] || isOfficeDoc) return
    apiClient
      .getDocumentUrl(caseId, currentDocumentId)
      .then((r) => {
        const url = r.signed_url || apiClient.getDocumentContentUrl(caseId, currentDocumentId)
        setSignedUrl(currentDocumentId, url)
      })
      .catch(() => {
        setSignedUrl(currentDocumentId, apiClient.getDocumentContentUrl(caseId, currentDocumentId))
      })
  }, [caseId, currentDocumentId, signedUrls, setSignedUrl, isOfficeDoc])

  const url = isOfficeDoc && currentDocumentId
    ? apiClient.getDocumentPreviewUrl(caseId, currentDocumentId)
    : currentDocumentId ? signedUrls[currentDocumentId] : null

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
            onClick={() =>
              setCurrentDoc({
                document_id: doc.document_id,
                page: 1,
                text_quote: '',
                confidence: 0,
              })
            }
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
          <PdfViewer url={url} page={currentPage} highlightText={highlightText} />
        ) : isImage ? (
          <ImageViewer url={url} />
        ) : isOfficeDoc ? (
          <HtmlViewer url={url} />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            未対応のファイル形式: .{ext}
          </div>
        )}
      </div>
    </div>
  )
}
