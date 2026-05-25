import { useState } from 'react'

interface Props {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
  fieldCount?: number
}

export default function FieldSection({
  title,
  children,
  defaultOpen = true,
  fieldCount,
}: Props) {
  const [open, setOpen] = useState(defaultOpen)

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
              {fieldCount}項目
            </span>
          )}
        </button>
      </div>
      {open && <div className="pb-1">{children}</div>}
    </div>
  )
}
