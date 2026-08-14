import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import {
  usePanZoom,
  applyZoomAnchor,
  clampScale,
  ZOOM_STEP,
  type ZoomAnchor,
} from './viewerZoomBehavior'
import { ViewerToolbar } from './viewerZoom'

const CONTENT_MARGIN = 16

interface Props {
  url: string
}

export default function ImageViewer({ url }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const pendingAnchorRef = useRef<ZoomAnchor | null>(null)
  const userZoomedRef = useRef(false)

  const [naturalWidth, setNaturalWidth] = useState<number | null>(null)
  const [scale, setScale] = useState<number | null>(null)

  const fitWidthScale = useCallback((imageWidth: number) => {
    const container = containerRef.current
    if (!container) return 1
    const available = container.clientWidth - CONTENT_MARGIN * 2
    if (available <= 0) return 1
    // 小さい画像は等倍のまま(ぼやけ防止)、大きい画像は幅に収める
    return clampScale(Math.min(1, available / imageWidth))
  }, [])

  const handleLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget
    setNaturalWidth(img.naturalWidth)
    setScale(fitWidthScale(img.naturalWidth))
    userZoomedRef.current = false
  }, [fitWidthScale])

  // ズーム後にアンカー点(カーソル直下)を維持する
  useLayoutEffect(() => {
    const container = containerRef.current
    const content = contentRef.current
    if (container && content && pendingAnchorRef.current) {
      applyZoomAnchor(container, content, pendingAnchorRef.current)
      pendingAnchorRef.current = null
    }
  }, [scale])

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

  usePanZoom(containerRef, contentRef, (factor, anchor) => {
    zoomBy(factor, anchor)
  })

  return (
    <div className="flex flex-col h-full">
      <ViewerToolbar
        zoomPercent={scale !== null ? Math.round(scale * 100) : 100}
        onZoomIn={() => zoomBy(ZOOM_STEP, centerAnchor())}
        onZoomOut={() => zoomBy(1 / ZOOM_STEP, centerAnchor())}
        onFitWidth={() => {
          if (naturalWidth !== null) {
            userZoomedRef.current = false
            setScale(fitWidthScale(naturalWidth))
          }
        }}
        onResetZoom={() => {
          userZoomedRef.current = true
          setScale(1)
        }}
      />
      <div ref={containerRef} className="flex-1 overflow-auto bg-gray-100 cursor-grab">
        <div
          ref={contentRef}
          className="shadow-lg bg-white"
          style={{ margin: CONTENT_MARGIN, width: 'fit-content', marginLeft: 'auto', marginRight: 'auto' }}
        >
          <img
            src={url}
            alt="書類"
            onLoad={handleLoad}
            draggable={false}
            className="block max-w-none"
            style={{
              width: naturalWidth !== null && scale !== null ? naturalWidth * scale : undefined,
              maxWidth: naturalWidth !== null && scale !== null ? 'none' : '100%',
            }}
          />
        </div>
      </div>
    </div>
  )
}
