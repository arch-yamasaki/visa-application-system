import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

export const MIN_SCALE = 0.25
export const MAX_SCALE = 4

export function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale))
}

export const ZOOM_STEP = 1.25

/** ズーム時にカーソル直下の点を維持するためのアンカー情報 */
export interface ZoomAnchor {
  /** コンテンツ左端からの割合 (0-1) */
  rx: number
  ry: number
  /** スクロールコンテナ内でのカーソル位置 (px) */
  offsetX: number
  offsetY: number
}

/**
 * スクロールコンテナに「ドラッグでパン」と「Cmd/Ctrl+ホイールでズーム」を付ける。
 * ホイールズームはトラックパッドのピンチ操作(Chromeでは ctrlKey 付き wheel)も拾う。
 */
export function usePanZoom(
  containerRef: RefObject<HTMLDivElement | null>,
  contentRef: RefObject<HTMLElement | null>,
  onZoom: (factor: number, anchor: ZoomAnchor) => void,
) {
  const onZoomRef = useRef(onZoom)
  onZoomRef.current = onZoom

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    let dragging = false
    let moved = false
    let startX = 0
    let startY = 0
    let startLeft = 0
    let startTop = 0

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return
      dragging = true
      moved = false
      startX = e.clientX
      startY = e.clientY
      startLeft = el.scrollLeft
      startTop = el.scrollTop
    }
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging) return
      const dx = e.clientX - startX
      const dy = e.clientY - startY
      if (!moved && Math.abs(dx) + Math.abs(dy) > 3) {
        moved = true
        el.style.cursor = 'grabbing'
        el.style.userSelect = 'none'
      }
      if (moved) {
        el.scrollLeft = startLeft - dx
        el.scrollTop = startTop - dy
      }
    }
    const endDrag = () => {
      if (!dragging) return
      dragging = false
      el.style.cursor = ''
      el.style.userSelect = ''
    }

    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      e.preventDefault()
      const content = contentRef.current
      const rect = el.getBoundingClientRect()
      const offsetX = e.clientX - rect.left
      const offsetY = e.clientY - rect.top
      const contentWidth = content?.offsetWidth || 1
      const contentHeight = content?.offsetHeight || 1
      const contentLeft = content?.offsetLeft || 0
      const contentTop = content?.offsetTop || 0
      const anchor: ZoomAnchor = {
        rx: (el.scrollLeft + offsetX - contentLeft) / contentWidth,
        ry: (el.scrollTop + offsetY - contentTop) / contentHeight,
        offsetX,
        offsetY,
      }
      const factor = Math.exp(-e.deltaY * 0.0025)
      onZoomRef.current(factor, anchor)
    }

    el.addEventListener('mousedown', onMouseDown)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', endDrag)
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      el.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', endDrag)
      el.removeEventListener('wheel', onWheel)
    }
  }, [containerRef, contentRef])
}

/** アンカー点がカーソル直下に留まるようスクロール位置を合わせる */
export function applyZoomAnchor(
  container: HTMLDivElement,
  content: HTMLElement,
  anchor: ZoomAnchor,
) {
  container.scrollLeft = anchor.rx * content.offsetWidth + content.offsetLeft - anchor.offsetX
  container.scrollTop = anchor.ry * content.offsetHeight + content.offsetTop - anchor.offsetY
}

interface ToolbarProps {
  zoomPercent: number
  onZoomIn: () => void
  onZoomOut: () => void
  onFitWidth: () => void
  onResetZoom: () => void
  page?: number
  numPages?: number
  onPrevPage?: () => void
  onNextPage?: () => void
}

export function ViewerToolbar({
  zoomPercent,
  onZoomIn,
  onZoomOut,
  onFitWidth,
  onResetZoom,
  page,
  numPages,
  onPrevPage,
  onNextPage,
}: ToolbarProps) {
  const btn =
    'px-2 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-30 disabled:hover:bg-white'
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-1.5 border-b border-gray-200 bg-gray-50 select-none">
      <div className="flex items-center gap-2">
        {numPages !== undefined && page !== undefined && (
          <>
            <button className={btn} onClick={onPrevPage} disabled={page <= 1}>
              前へ
            </button>
            <span className="text-xs text-gray-500 tabular-nums">
              {page} / {numPages}
            </span>
            <button className={btn} onClick={onNextPage} disabled={page >= numPages}>
              次へ
            </button>
          </>
        )}
      </div>
      <div className="flex items-center gap-1">
        <button className={btn} onClick={onZoomOut} title="縮小" aria-label="縮小">
          −
        </button>
        <button
          className="w-14 py-1 text-xs text-gray-600 tabular-nums text-center bg-white border border-gray-300 rounded hover:bg-gray-50"
          onClick={onResetZoom}
          title="100%に戻す"
        >
          {zoomPercent}%
        </button>
        <button className={btn} onClick={onZoomIn} title="拡大" aria-label="拡大">
          ＋
        </button>
        <button className={`${btn} ml-1`} onClick={onFitWidth} title="幅に合わせる">
          幅に合わせる
        </button>
      </div>
    </div>
  )
}
