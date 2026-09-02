import { useEffect, useMemo, useRef, useState } from 'react'
import { authHeaders } from '../../auth/firebase'
import type { SourceRef } from '../../types/caseData'
import { useViewerStore } from '../../store/viewerStore'

interface Props {
  url: string
  sourceRef?: SourceRef | null
  sheets?: string[]
  onSheetChange?: (sheet: string) => void
}

function anchorSelectorValue(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function anchorId(sourceRef: SourceRef | null | undefined): string | null {
  const anchor = sourceRef?.anchor
  if (anchor?.status !== 'resolved') return null
  if (anchor.anchor_id) return anchor.anchor_id
  if (anchor.type === 'xlsx_cell' && anchor.sheet_name && anchor.cell) {
    return `${anchor.sheet_name}!${anchor.cell}`
  }
  return null
}

type SourceAnchorCandidate = NonNullable<NonNullable<SourceRef['anchor']>['candidates']>[number]

function candidateAnchorId(candidate: SourceAnchorCandidate): string | null {
  if (candidate.anchor_id) return candidate.anchor_id
  if (candidate.sheet_name && candidate.cell) return `${candidate.sheet_name}!${candidate.cell}`
  return null
}

function activeSheetName(sourceRef: SourceRef | null | undefined, activeCandidateIndex: number): string | undefined {
  const anchor = sourceRef?.anchor
  if (anchor?.status === 'resolved') return anchor.sheet_name
  if (anchor?.status !== 'ambiguous') return undefined
  return anchor.candidates?.[activeCandidateIndex]?.sheet_name
}

export default function HtmlViewer({ url, sourceRef, sheets, onSheetChange }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [activeSheet, setActiveSheet] = useState(sheets?.[0] ?? '')
  const [html, setHtml] = useState('')
  const activeCandidateIndex = useViewerStore((s) => s.activeCandidateIndex)
  const goToCandidate = useViewerStore((s) => s.goToCandidate)

  const candidates = useMemo(
    () => sourceRef?.anchor?.status === 'ambiguous' ? sourceRef.anchor.candidates ?? [] : [],
    [sourceRef],
  )
  const candidateCount = candidates.length

  // preview API は認証必須のため、iframe src ではなく fetch + srcDoc で読み込む
  useEffect(() => {
    let cancelled = false
    setHtml('')
    ;(async () => {
      const res = await fetch(url, { headers: await authHeaders() })
      const text = await res.text()
      if (!cancelled) setHtml(text)
    })()
    return () => {
      cancelled = true
    }
  }, [url])

  // sheets が非同期で届いた場合に初期選択
  useEffect(() => {
    if (sheets?.length && !activeSheet) setActiveSheet(sheets[0])
  }, [activeSheet, sheets])

  useEffect(() => {
    const sheetName = activeSheetName(sourceRef, activeCandidateIndex)
    if (sheetName && sheetName !== activeSheet) {
      setActiveSheet(sheetName)
      onSheetChange?.(sheetName)
    }
  }, [activeCandidateIndex, activeSheet, onSheetChange, sourceRef])

  // iframe ロード後にbackendが検証済みのanchorだけをハイライトする
  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe) return

    /** 既存の <mark> を全て unwrap してクリアする */
    const clearHighlights = (doc: Document) => {
      doc.querySelectorAll('mark').forEach((mark) => {
        const parent = mark.parentNode
        if (parent) {
          while (mark.firstChild) parent.insertBefore(mark.firstChild, mark)
          parent.removeChild(mark)
        }
      })
      doc.querySelectorAll<HTMLElement>('[data-anchor-highlight="true"]').forEach((el) => {
        el.style.backgroundColor = ''
        el.style.outline = ''
        el.style.borderRadius = ''
        delete el.dataset.anchorHighlight
      })
    }

    const handleLoad = () => {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document
        if (!doc?.body) return

        // 前回のハイライトをクリア
        clearHighlights(doc)

        const resolvedAnchorId = anchorId(sourceRef)
        if (resolvedAnchorId) {
          const target = doc.querySelector<HTMLElement>(`[data-anchor="${anchorSelectorValue(resolvedAnchorId)}"]`)
          if (target) {
            target.dataset.anchorHighlight = 'true'
            target.style.backgroundColor = 'rgba(255, 160, 0, 0.35)'
            target.style.outline = '2px solid rgba(255, 140, 0, 0.8)'
            target.style.borderRadius = '2px'
            target.scrollIntoView({ behavior: 'smooth', block: 'center' })
            return
          }
        }

        if (sourceRef?.anchor?.status === 'ambiguous') {
          let activeTarget: HTMLElement | null = null
          for (const [index, candidate] of candidates.entries()) {
            const targetAnchorId = candidateAnchorId(candidate)
            if (!targetAnchorId) continue
            const target = doc.querySelector<HTMLElement>(`[data-anchor="${anchorSelectorValue(targetAnchorId)}"]`)
            if (!target) continue
            target.dataset.anchorHighlight = 'true'
            target.style.backgroundColor = index === activeCandidateIndex
              ? 'rgba(255, 160, 0, 0.35)'
              : 'rgba(255, 160, 0, 0.2)'
            target.style.outline = index === activeCandidateIndex
              ? '2px solid rgba(234, 88, 12, 1)'
              : '2px dashed rgba(255, 140, 0, 0.8)'
            target.style.borderRadius = '2px'
            if (index === activeCandidateIndex) {
              activeTarget = target
            }
          }
          activeTarget?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      } catch {
        // cross-origin の場合は無視（ハイライトなしで表示）
      }
    }

    iframe.addEventListener('load', handleLoad)
    if (iframe.contentDocument?.readyState === 'complete') {
      handleLoad()
    }
    return () => iframe.removeEventListener('load', handleLoad)
  }, [activeCandidateIndex, candidates, sourceRef, url])

  const handleSheetClick = (sheet: string) => {
    setActiveSheet(sheet)
    onSheetChange?.(sheet)
  }

  return (
    <div className="relative flex flex-col h-full">
      {candidateCount > 1 && (
        <div className="absolute top-12 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 bg-white/95 border border-amber-300 rounded-full shadow px-2 py-1 text-xs text-amber-800">
          <button
            onClick={() => goToCandidate((activeCandidateIndex - 1 + candidateCount) % candidateCount)}
            className="px-1.5 py-0.5 rounded-full hover:bg-amber-100"
            aria-label="前の根拠位置へ"
            title="前の根拠位置へ"
          >
            ←
          </button>
          <span className="whitespace-nowrap" aria-live="polite">
            根拠 {Math.min(activeCandidateIndex + 1, candidateCount)}/{candidateCount}
          </span>
          <button
            onClick={() => goToCandidate((activeCandidateIndex + 1) % candidateCount)}
            className="px-1.5 py-0.5 rounded-full hover:bg-amber-100"
            aria-label="次の根拠位置へ"
            title="次の根拠位置へ"
          >
            →
          </button>
        </div>
      )}
      {sheets && sheets.length > 1 && (
        <div className="flex border-b border-gray-200 bg-gray-50 px-2 pt-1 overflow-x-auto shrink-0">
          {sheets.map((s) => (
            <button
              key={s}
              onClick={() => handleSheetClick(s)}
              className={`px-3 py-1.5 text-xs whitespace-nowrap rounded-t border border-b-0 mr-0.5 transition-colors ${
                s === activeSheet
                  ? 'bg-white text-blue-700 border-gray-300 font-medium'
                  : 'bg-gray-100 text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-200'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <iframe
        ref={iframeRef}
        srcDoc={html}
        className="w-full flex-1 border-0"
        title="書類プレビュー"
      />
    </div>
  )
}
