import { useState } from 'react'

interface Props {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
  fieldCount?: number
  reviewedCount?: number
  onMarkAllReviewed?: () => void
}

export default function FieldSection({
  title,
  children,
  defaultOpen = true,
  fieldCount,
  reviewedCount,
  onMarkAllReviewed,
}: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const allReviewed = fieldCount !== undefined && reviewedCount !== undefined && reviewedCount >= fieldCount

  return (
    <div className="border-b border-gray-200">
      <div className="flex items-center bg-gray-50">
        <button
          onClick={() => setOpen(!open)}
          className="flex-1 flex items-center gap-2 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100 transition-colors"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
          >
            <path d="M4 2L9 6L4 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {title}
          {fieldCount !== undefined && (
            <span className="text-[10px] font-normal text-gray-400 ml-1">
              ({reviewedCount ?? 0}/{fieldCount})
            </span>
          )}
        </button>
        {onMarkAllReviewed && !allReviewed && (
          <button
            onClick={(e) => { e.stopPropagation(); onMarkAllReviewed() }}
            className="mr-2 px-2 py-0.5 text-[10px] text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded transition-colors"
          >
            全て確認済み
          </button>
        )}
        {allReviewed && (
          <span className="mr-2 px-2 py-0.5 text-[10px] text-green-600 font-medium">
            確認完了
          </span>
        )}
      </div>
      {open && <div className="pb-1">{children}</div>}
    </div>
  )
}
