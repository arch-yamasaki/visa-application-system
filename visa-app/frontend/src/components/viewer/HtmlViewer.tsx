import { useEffect, useRef, useState } from 'react'

interface Props {
  url: string
  highlightText?: string | null
  sheets?: string[]
  onSheetChange?: (sheet: string) => void
}

export default function HtmlViewer({ url, highlightText, sheets, onSheetChange }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [activeSheet, setActiveSheet] = useState(sheets?.[0] ?? '')

  // sheets が非同期で届いた場合に初期選択
  useEffect(() => {
    if (sheets?.length && !activeSheet) setActiveSheet(sheets[0])
  }, [sheets])

  // iframe ロード後にハイライトテキストを検索
  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe || !highlightText?.trim()) return

    const handleLoad = () => {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document
        if (!doc?.body) return

        const text = highlightText.trim()
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
  }, [url, highlightText])

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
        src={url}
        className="w-full flex-1 border-0"
        title="書類プレビュー"
      />
    </div>
  )
}
