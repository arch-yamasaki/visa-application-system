import { useEffect, useRef, useState } from 'react'
import { authHeaders } from '../../auth/firebase'
import type { SourceRef } from '../../types/caseData'

interface Props {
  url: string
  highlightText?: string | null
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

export default function HtmlViewer({ url, highlightText, sourceRef, sheets, onSheetChange }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [activeSheet, setActiveSheet] = useState(sheets?.[0] ?? '')
  const [html, setHtml] = useState('')

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
    const sheetName = sourceRef?.anchor?.status === 'resolved' ? sourceRef.anchor.sheet_name : undefined
    if (sheetName && sheetName !== activeSheet) {
      setActiveSheet(sheetName)
      onSheetChange?.(sheetName)
    }
  }, [activeSheet, onSheetChange, sourceRef])

  // iframe ロード後にハイライトテキストを検索
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

        const text = highlightText?.trim()
        if (!text) return

        const walker = document.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT)
        const normalizedSearch = text.replace(/\s+/g, '').toLowerCase()
        let node: Text | null

        while ((node = walker.nextNode() as Text | null)) {
          // td 祖先があればそのセル全体のテキストで完全一致判定
          const td = node.parentElement?.closest('td')
          const compareText = (td ?? node).textContent?.replace(/\s+/g, '').toLowerCase() ?? ''
          if (compareText.indexOf(normalizedSearch) === -1) continue

          // td 内テキスト全体が一致 → そのセルだけハイライトして終了
          const parent = node.parentElement
          if (parent) {
            const mark = doc.createElement('mark')
            mark.style.backgroundColor = 'rgba(255, 160, 0, 0.45)'
            mark.style.border = '1px solid rgba(255, 140, 0, 0.7)'
            mark.style.borderRadius = '2px'
            parent.replaceChild(mark, node)
            mark.appendChild(node)
            mark.scrollIntoView({ behavior: 'smooth', block: 'center' })
          }
          break
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
  }, [url, highlightText, sourceRef])

  const handleSheetClick = (sheet: string) => {
    setActiveSheet(sheet)
    onSheetChange?.(sheet)
  }

  return (
    <div className="flex flex-col h-full">
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
