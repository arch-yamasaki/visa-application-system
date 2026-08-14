import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

const MIN_SCALE = 0.25
const MAX_SCALE = 4
export const ZOOM_STEP = 1.25

export function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale))
}

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

  useEffect(() => {
    onZoomRef.current = onZoom
  }, [onZoom])

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
