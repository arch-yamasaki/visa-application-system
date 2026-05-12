import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { TextItem } from 'pdfjs-dist/types/src/display/api'
import { useViewerStore } from '../../store/viewerStore'

// Configure pdf.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

interface Props {
  url: string
  page: number
  highlightText: string | null
}

export default function PdfViewer({ url, page, highlightText }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const highlightRef = useRef<HTMLDivElement>(null)
  const [numPages, setNumPages] = useState(0)
  const [scale] = useState(1.5)
  const setPage = useViewerStore((s) => s.setPage)

  useEffect(() => {
    let cancelled = false
    const loadTask = pdfjsLib.getDocument(url)

    loadTask.promise.then(async (pdf) => {
      if (cancelled) return
      setNumPages(pdf.numPages)

      const pageNum = Math.min(Math.max(1, page), pdf.numPages)
      const pdfPage = await pdf.getPage(pageNum)
      const viewport = pdfPage.getViewport({ scale })

      // Render canvas
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      canvas.width = viewport.width
      canvas.height = viewport.height

      await pdfPage.render({
        canvasContext: ctx,
        viewport,
      } as unknown as Parameters<typeof pdfPage.render>[0]).promise

      // Highlight using text content positions
      const overlay = highlightRef.current
      if (!overlay) return
      overlay.innerHTML = ''
      overlay.style.width = `${viewport.width}px`
      overlay.style.height = `${viewport.height}px`

      if (highlightText && highlightText.trim()) {
        const textContent = await pdfPage.getTextContent()
        highlightTextOnCanvas(overlay, textContent.items as TextItem[], viewport, highlightText.trim())
      }
    })

    return () => {
      cancelled = true
      loadTask.destroy()
    }
  }, [url, page, scale, highlightText])

  return (
    <div className="relative p-4">
      {numPages > 1 && (
        <div className="flex items-center justify-center gap-3 mb-3">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="px-2 py-1 text-xs bg-white border rounded disabled:opacity-30"
          >
            Prev
          </button>
          <span className="text-xs text-gray-500">
            Page {page} / {numPages}
          </span>
          <button
            onClick={() => setPage(Math.min(numPages, page + 1))}
            disabled={page >= numPages}
            className="px-2 py-1 text-xs bg-white border rounded disabled:opacity-30"
          >
            Next
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

/** Use pdf.js text item positions to draw highlight rectangles on matching text. */
function highlightTextOnCanvas(
  overlay: HTMLElement,
  items: TextItem[],
  viewport: pdfjsLib.PageViewport,
  quote: string,
) {
  const normalizedQuote = quote.replace(/\s+/g, '').toLowerCase()

  // Build a text buffer with item indices
  let fullText = ''
  const itemRanges: { start: number; end: number; item: TextItem }[] = []

  for (const item of items) {
    if (!item.str) continue
    const start = fullText.length
    fullText += item.str.replace(/\s+/g, '').toLowerCase()
    itemRanges.push({ start, end: fullText.length, item })
  }

  const matchIdx = fullText.indexOf(normalizedQuote)
  if (matchIdx === -1) return

  const matchEnd = matchIdx + normalizedQuote.length

  // Find overlapping items
  for (const { start, end, item } of itemRanges) {
    if (end <= matchIdx || start >= matchEnd) continue

    // Get the item's transform: [scaleX, skewX, skewY, scaleY, translateX, translateY]
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
    div.style.backgroundColor = 'rgba(255, 200, 0, 0.4)'
    div.style.borderRadius = '2px'
    overlay.appendChild(div)
  }

  // Scroll first highlight into view
  const first = overlay.firstElementChild as HTMLElement | null
  first?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
