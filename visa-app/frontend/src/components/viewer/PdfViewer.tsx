import { useCallback, useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, TextItem } from 'pdfjs-dist/types/src/display/api'
import { useViewerStore } from '../../store/viewerStore'
import type { SourceRef } from '../../types/caseData'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

const WASM_URL = '/'

interface Props {
  url: string
  page: number
  highlightText: string | null
  sourceRef?: SourceRef | null
}

export default function PdfViewer({ url, page, highlightText, sourceRef }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const highlightRef = useRef<HTMLDivElement>(null)
  const [numPages, setNumPages] = useState(0)
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const scale = 1.5
  const setPage = useViewerStore((s) => s.setPage)

  // Load PDF document
  useEffect(() => {
    let destroyed = false
    setPdfDoc(null)
    setNumPages(0)
    setLoadError(null)

    const task = pdfjsLib.getDocument({ url, wasmUrl: WASM_URL })
    task.promise.then((pdf) => {
      if (!destroyed) {
        setPdfDoc(pdf)
        setNumPages(pdf.numPages)
      }
    }).catch((err) => {
      if (!destroyed) {
        console.error('PDF load failed:', err)
        setLoadError('PDF読み込みに失敗しました')
      }
    })

    return () => {
      destroyed = true
      task.destroy().catch(() => {})
    }
  }, [url])

  // Render current page
  const renderPage = useCallback(async (doc: PDFDocumentProxy, pageNum: number) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const pdfPage = await doc.getPage(pageNum)
    const viewport = pdfPage.getViewport({ scale })

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    canvas.width = viewport.width
    canvas.height = viewport.height

    await (pdfPage.render({
      canvasContext: ctx,
      viewport,
    } as unknown as Parameters<typeof pdfPage.render>[0]).promise)

    // Highlight
    const overlay = highlightRef.current
    if (!overlay) return
    overlay.innerHTML = ''
    overlay.style.width = `${viewport.width}px`
    overlay.style.height = `${viewport.height}px`

    if (sourceRef?.bbox) {
      const { y_min, x_min, y_max, x_max } = sourceRef.bbox
      const div = document.createElement('div')
      div.style.position = 'absolute'
      div.style.left = `${(x_min / 1000) * viewport.width}px`
      div.style.top = `${(y_min / 1000) * viewport.height}px`
      div.style.width = `${((x_max - x_min) / 1000) * viewport.width}px`
      div.style.height = `${((y_max - y_min) / 1000) * viewport.height}px`
      div.style.backgroundColor = 'rgba(255, 160, 0, 0.45)'
      div.style.border = '1px solid rgba(255, 140, 0, 0.7)'
      div.style.borderRadius = '2px'
      overlay.appendChild(div)
      div.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } else if (highlightText?.trim()) {
      const textContent = await pdfPage.getTextContent()
      highlightTextOnCanvas(overlay, textContent.items as TextItem[], viewport, highlightText.trim())
    }
  }, [scale, highlightText, sourceRef])

  useEffect(() => {
    if (!pdfDoc) return
    const pageNum = Math.min(Math.max(1, page), pdfDoc.numPages)
    renderPage(pdfDoc, pageNum).catch(() => {})
  }, [pdfDoc, page, renderPage])

  return (
    <div className="relative p-4">
      {loadError ? (
        <div className="flex items-center justify-center h-64 text-red-500 text-sm">
          {loadError}
        </div>
      ) : !pdfDoc ? (
        <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
          <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mr-2" />
          PDFを読み込み中...
        </div>
      ) : null}

      {numPages > 1 && (
        <div className="flex items-center justify-center gap-3 mb-3">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-2 py-1 text-xs bg-white border rounded disabled:opacity-30"
          >
            前へ
          </button>
          <span className="text-xs text-gray-500">
            {page} / {numPages} ページ
          </span>
          <button
            onClick={() => setPage(Math.min(numPages, page + 1))}
            disabled={page >= numPages}
            className="px-2 py-1 text-xs bg-white border rounded disabled:opacity-30"
          >
            次へ
          </button>
        </div>
      )}

      <div className="relative inline-block shadow-lg">
        <canvas ref={canvasRef} />
        <div
          ref={highlightRef}
          className="absolute top-0 left-0 pointer-events-none"
        />
      </div>
    </div>
  )
}

function normalizeText(s: string): string {
  return s
    .normalize('NFKC')
    .replace(/[\s\u3000]+/g, '')
    .replace(/[、。,.，．]/g, '')
    .toLowerCase()
}

function highlightTextOnCanvas(
  overlay: HTMLElement,
  items: TextItem[],
  viewport: pdfjsLib.PageViewport,
  quote: string,
) {
  const normalizedQuote = normalizeText(quote)

  let fullText = ''
  const itemRanges: { start: number; end: number; item: TextItem }[] = []
  for (const item of items) {
    if (!item.str) continue
    const start = fullText.length
    fullText += normalizeText(item.str)
    itemRanges.push({ start, end: fullText.length, item })
  }

  // Try full match first, then partial match fallback
  let matchIdx = fullText.indexOf(normalizedQuote)
  let matchLen = normalizedQuote.length

  if (matchIdx === -1 && normalizedQuote.length > 10) {
    // Try progressively shorter prefixes (minimum 10 chars)
    for (let len = normalizedQuote.length - 1; len >= 10; len--) {
      const partial = normalizedQuote.slice(0, len)
      const idx = fullText.indexOf(partial)
      if (idx !== -1) {
        matchIdx = idx
        matchLen = len
        break
      }
    }
  }

  if (matchIdx === -1) return

  const matchEnd = matchIdx + matchLen
  for (const { start, end, item } of itemRanges) {
    if (end <= matchIdx || start >= matchEnd) continue
    const tx = pdfjsLib.Util.transform(viewport.transform, item.transform)
    const x = tx[4]
    const y = tx[5]
    const fontSize = Math.sqrt(tx[2] * tx[2] + tx[3] * tx[3])
    const width = item.width * viewport.scale

    const div = document.createElement('div')
    div.style.position = 'absolute'
    div.style.left = `${x}px`
    div.style.top = `${y - fontSize}px`
    div.style.width = `${width}px`
    div.style.height = `${fontSize * 1.2}px`
    div.style.backgroundColor = 'rgba(255, 160, 0, 0.45)'
    div.style.border = '1px solid rgba(255, 140, 0, 0.7)'
    div.style.borderRadius = '2px'
    overlay.appendChild(div)
  }

  const first = overlay.firstElementChild as HTMLElement | null
  first?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
