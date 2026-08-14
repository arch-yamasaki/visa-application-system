import { useCallback, useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, RenderTask, TextItem } from 'pdfjs-dist/types/src/display/api'
import { useViewerStore } from '../../store/viewerStore'
import type { SourceRef } from '../../types/caseData'
import {
  usePanZoom,
  applyZoomAnchor,
  clampScale,
  ZOOM_STEP,
  type ZoomAnchor,
} from './viewerZoomBehavior'
import { ViewerToolbar } from './viewerZoom'

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

const WASM_URL = '/'
const CONTENT_MARGIN = 16

interface Props {
  url: string
  page: number
  highlightText: string | null
  sourceRef?: SourceRef | null
}

export default function PdfViewer({ url, page, highlightText, sourceRef }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const highlightRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const renderTaskRef = useRef<RenderTask | null>(null)
  const pendingAnchorRef = useRef<ZoomAnchor | null>(null)
  const lastScrollKeyRef = useRef<string | null>(null)
  const userZoomedRef = useRef(false)
  const wheelRafRef = useRef<number | null>(null)
  const wheelScaleRef = useRef<number | null>(null)

  const [numPages, setNumPages] = useState(0)
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [scale, setScale] = useState<number | null>(null)
  const setPage = useViewerStore((s) => s.setPage)
  const activeCandidateIndex = useViewerStore((s) => s.activeCandidateIndex)
  const goToCandidate = useViewerStore((s) => s.goToCandidate)

  const candidates = sourceRef?.anchor?.status === 'ambiguous' ? sourceRef.anchor.candidates ?? [] : []
  const candidateCount = candidates.length

  // Load PDF document
  useEffect(() => {
    let destroyed = false
    setPdfDoc(null)
    setNumPages(0)
    setLoadError(null)
    setScale(null)
    userZoomedRef.current = false
    lastScrollKeyRef.current = null

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

  const computeFitWidthScale = useCallback(async (doc: PDFDocumentProxy, pageNum: number) => {
    const container = containerRef.current
    if (!container) return null
    const pdfPage = await doc.getPage(Math.min(Math.max(1, pageNum), doc.numPages))
    const baseViewport = pdfPage.getViewport({ scale: 1 })
    const available = container.clientWidth - CONTENT_MARGIN * 2
    if (available <= 0) return null
    return clampScale(available / baseViewport.width)
  }, [])

  // Initial scale: fit width (デフォルトではみ出さない)
  useEffect(() => {
    if (!pdfDoc || scale !== null) return
    let cancelled = false
    computeFitWidthScale(pdfDoc, page).then((fit) => {
      if (!cancelled && fit !== null) setScale(fit)
    })
    return () => {
      cancelled = true
    }
  }, [pdfDoc, scale, page, computeFitWidthScale])

  // ペイン幅の変化に追従(ユーザーが手動ズームするまで)
  useEffect(() => {
    const container = containerRef.current
    if (!container || !pdfDoc) return
    const observer = new ResizeObserver(() => {
      if (userZoomedRef.current) return
      computeFitWidthScale(pdfDoc, page).then((fit) => {
        if (fit !== null) setScale(fit)
      })
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [pdfDoc, page, computeFitWidthScale])

  // Render current page
  const renderPage = useCallback(async (doc: PDFDocumentProxy, pageNum: number, pageScale: number) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const pdfPage = await doc.getPage(pageNum)
    const dpr = window.devicePixelRatio || 1
    const renderViewport = pdfPage.getViewport({ scale: pageScale * dpr })
    const viewport = pdfPage.getViewport({ scale: pageScale })

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    canvas.width = renderViewport.width
    canvas.height = renderViewport.height
    canvas.style.width = `${viewport.width}px`
    canvas.style.height = `${viewport.height}px`

    // canvasサイズ確定直後に、ズームアンカー(カーソル直下の点)を維持する
    const container = containerRef.current
    const content = contentRef.current
    if (container && content && pendingAnchorRef.current) {
      applyZoomAnchor(container, content, pendingAnchorRef.current)
      pendingAnchorRef.current = null
    }

    renderTaskRef.current?.cancel()
    const task = pdfPage.render({
      canvasContext: ctx,
      viewport: renderViewport,
    } as unknown as Parameters<typeof pdfPage.render>[0])
    renderTaskRef.current = task
    try {
      await task.promise
    } catch {
      return // cancelled (連続ズーム中の描画破棄)
    }

    // Highlight
    const overlay = highlightRef.current
    if (!overlay) return
    overlay.innerHTML = ''
    overlay.style.width = `${viewport.width}px`
    overlay.style.height = `${viewport.height}px`

    // ambiguous は単一確定にせず、保存された候補位置を「候補」スタイルで全て見せる。
    // not_found や status なしの場合、legacy top-level bbox は別経路(Gemini bbox)由来の根拠なので表示してよい。
    const anchorStatus = sourceRef?.anchor?.status
    const bbox =
      anchorStatus === 'resolved'
        ? sourceRef?.anchor?.bbox ?? sourceRef?.bbox
        : anchorStatus === 'ambiguous'
          ? null
          : sourceRef?.bbox
    const candidateEntries =
      anchorStatus === 'ambiguous'
        ? (sourceRef?.anchor?.candidates ?? [])
            .map((candidate, index) => ({ candidate, index }))
            .filter(({ candidate }) => (candidate.page ?? sourceRef?.page ?? pageNum) === pageNum)
        : []
    const scrollKey = `${pageNum}:${
      bbox
        ? JSON.stringify(bbox)
        : candidateEntries.length
          ? `${JSON.stringify(candidateEntries)}:${activeCandidateIndex}`
          : highlightText ?? ''
    }`
    // ズームによる再描画では highlight へ再スクロールしない
    const shouldScroll = scrollKey !== lastScrollKeyRef.current
    lastScrollKeyRef.current = scrollKey

    if (bbox) {
      const div = appendBboxDiv(overlay, viewport, bbox, 'resolved')
      if (shouldScroll) div.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } else if (candidateEntries.length > 0) {
      let activeDiv: HTMLElement | null = null
      for (const { candidate, index } of candidateEntries) {
        const div = appendBboxDiv(
          overlay,
          viewport,
          candidate.bbox,
          index === activeCandidateIndex ? 'candidate-active' : 'candidate',
        )
        if (index === activeCandidateIndex) activeDiv = div
      }
      if (shouldScroll) {
        const target = activeDiv ?? (overlay.firstElementChild as HTMLElement | null)
        target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    } else if (highlightText?.trim()) {
      const textContent = await pdfPage.getTextContent()
      highlightTextOnCanvas(overlay, textContent.items as TextItem[], viewport, highlightText.trim(), shouldScroll)
    }
  }, [highlightText, sourceRef, activeCandidateIndex])

  useEffect(() => {
    if (!pdfDoc || scale === null) return
    const pageNum = Math.min(Math.max(1, page), pdfDoc.numPages)
    renderPage(pdfDoc, pageNum, scale).catch(() => {})
  }, [pdfDoc, page, scale, renderPage])

  const zoomBy = useCallback((factor: number, anchor?: ZoomAnchor) => {
    userZoomedRef.current = true
    setScale((prev) => {
      if (prev === null) return prev
      const next = clampScale(prev * factor)
      if (next !== prev && anchor) pendingAnchorRef.current = anchor
      return next
    })
  }, [])

  const centerAnchor = useCallback((): ZoomAnchor | undefined => {
    const container = containerRef.current
    const content = contentRef.current
    if (!container || !content) return undefined
    const offsetX = container.clientWidth / 2
    const offsetY = container.clientHeight / 2
    return {
      rx: (container.scrollLeft + offsetX - content.offsetLeft) / (content.offsetWidth || 1),
      ry: (container.scrollTop + offsetY - content.offsetTop) / (content.offsetHeight || 1),
      offsetX,
      offsetY,
    }
  }, [])

  // Cmd/Ctrl+ホイール(ピンチ)ズーム: rAFで連続イベントをまとめる
  usePanZoom(containerRef, contentRef, (factor, anchor) => {
    wheelScaleRef.current = (wheelScaleRef.current ?? 1) * factor
    pendingAnchorRef.current = anchor
    if (wheelRafRef.current !== null) return
    wheelRafRef.current = requestAnimationFrame(() => {
      wheelRafRef.current = null
      const accumulated = wheelScaleRef.current ?? 1
      wheelScaleRef.current = null
      zoomBy(accumulated, pendingAnchorRef.current ?? undefined)
    })
  })

  const handleFitWidth = useCallback(() => {
    if (!pdfDoc) return
    userZoomedRef.current = false
    computeFitWidthScale(pdfDoc, page).then((fit) => {
      if (fit !== null) setScale(fit)
    })
  }, [pdfDoc, page, computeFitWidthScale])

  const handleResetZoom = useCallback(() => {
    userZoomedRef.current = true
    setScale((prev) => {
      if (prev !== null && prev !== 1) pendingAnchorRef.current = null
      return 1
    })
  }, [])

  return (
    <div className="flex flex-col h-full">
      <ViewerToolbar
        zoomPercent={scale !== null ? Math.round(scale * 100) : 100}
        onZoomIn={() => zoomBy(ZOOM_STEP, centerAnchor())}
        onZoomOut={() => zoomBy(1 / ZOOM_STEP, centerAnchor())}
        onFitWidth={handleFitWidth}
        onResetZoom={handleResetZoom}
        page={page}
        numPages={numPages || 1}
        onPrevPage={() => setPage(Math.max(1, page - 1))}
        onNextPage={() => setPage(Math.min(numPages, page + 1))}
      />
      <div className="relative flex-1 min-h-0">
        {candidateCount > 1 && (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 bg-white/95 border border-amber-300 rounded-full shadow px-2 py-1 text-xs text-amber-800">
            <button
              onClick={() => goToCandidate((activeCandidateIndex - 1 + candidateCount) % candidateCount)}
              className="px-1.5 py-0.5 rounded-full hover:bg-amber-100"
              title="前の候補へ"
            >
              ←
            </button>
            <span className="whitespace-nowrap">
              候補 {Math.min(activeCandidateIndex + 1, candidateCount)}/{candidateCount}
            </span>
            <button
              onClick={() => goToCandidate((activeCandidateIndex + 1) % candidateCount)}
              className="px-1.5 py-0.5 rounded-full hover:bg-amber-100"
              title="次の候補へ"
            >
              →
            </button>
          </div>
        )}
      <div ref={containerRef} className="h-full overflow-auto bg-gray-100 cursor-grab">
        {loadError ? (
          <div className="flex items-center justify-center h-64 text-red-500 text-sm">
            {loadError}
          </div>
        ) : !pdfDoc || scale === null ? (
          <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
            <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin mr-2" />
            PDFを読み込み中...
          </div>
        ) : null}
        <div
          ref={contentRef}
          className="relative shadow-lg bg-white"
          style={{ margin: CONTENT_MARGIN, width: 'fit-content', marginLeft: 'auto', marginRight: 'auto' }}
        >
          <canvas ref={canvasRef} className="block" />
          <div
            ref={highlightRef}
            className="absolute top-0 left-0 pointer-events-none"
          />
        </div>
      </div>
      </div>
    </div>
  )
}

function appendBboxDiv(
  overlay: HTMLElement,
  viewport: pdfjsLib.PageViewport,
  bbox: { y_min: number; x_min: number; y_max: number; x_max: number },
  variant: 'resolved' | 'candidate' | 'candidate-active',
): HTMLElement {
  const { y_min, x_min, y_max, x_max } = bbox
  const div = document.createElement('div')
  div.style.position = 'absolute'
  div.style.left = `${(x_min / 1000) * viewport.width}px`
  div.style.top = `${(y_min / 1000) * viewport.height}px`
  div.style.width = `${((x_max - x_min) / 1000) * viewport.width}px`
  div.style.height = `${((y_max - y_min) / 1000) * viewport.height}px`
  if (variant === 'candidate') {
    div.style.backgroundColor = 'rgba(255, 160, 0, 0.2)'
    div.style.border = '2px dashed rgba(255, 140, 0, 0.9)'
  } else if (variant === 'candidate-active') {
    div.style.backgroundColor = 'rgba(255, 160, 0, 0.35)'
    div.style.border = '2px dashed rgba(234, 88, 12, 1)'
    div.style.boxShadow = '0 0 0 2px rgba(234, 88, 12, 0.25)'
  } else {
    div.style.backgroundColor = 'rgba(255, 160, 0, 0.45)'
    div.style.border = '1px solid rgba(255, 140, 0, 0.7)'
  }
  div.style.borderRadius = '2px'
  overlay.appendChild(div)
  return div
}

function normalizeText(s: string): string {
  return s
    .normalize('NFKC')
    .replace(/\s+/g, '')
    .replace(/[、。,.，．()（）]/g, '')
    .toLowerCase()
}

function highlightTextOnCanvas(
  overlay: HTMLElement,
  items: TextItem[],
  viewport: pdfjsLib.PageViewport,
  quote: string,
  shouldScroll: boolean,
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

  if (shouldScroll) {
    const first = overlay.firstElementChild as HTMLElement | null
    first?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}
