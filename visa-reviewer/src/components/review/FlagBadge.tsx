interface Props {
  type: 'ok' | 'needs_review' | 'missing' | 'error' | 'edited'
}

const CheckIcon = () => (
  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="inline-block">
    <path d="M13.5 4.5L6.5 11.5L2.5 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const WarningIcon = () => (
  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="inline-block">
    <path d="M8 1L15 14H1L8 1Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M8 6V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="8" cy="11.5" r="0.75" fill="currentColor" />
  </svg>
)

const ErrorIcon = () => (
  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="inline-block">
    <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M5.5 5.5L10.5 10.5M10.5 5.5L5.5 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
)

const EditIcon = () => (
  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="inline-block">
    <path d="M11 2L14 5L5 14H2V11L11 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
)

const MissingIcon = () => (
  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="inline-block">
    <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M6 6C6 4.9 6.9 4 8 4C9.1 4 10 4.9 10 6C10 7 9 7.2 8.5 8V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="8.5" cy="11" r="0.75" fill="currentColor" />
  </svg>
)

const config: Record<string, { label: string; className: string; icon: React.FC }> = {
  ok: { label: 'OK', className: 'bg-green-100 text-green-700', icon: CheckIcon },
  needs_review: { label: '要確認', className: 'bg-orange-100 text-orange-700', icon: WarningIcon },
  missing: { label: '不足', className: 'bg-red-100 text-red-700', icon: MissingIcon },
  error: { label: 'エラー', className: 'bg-red-100 text-red-700', icon: ErrorIcon },
  edited: { label: '編集済', className: 'bg-blue-100 text-blue-700', icon: EditIcon },
}

export default function FlagBadge({ type }: Props) {
  const c = config[type] ?? config.ok
  const Icon = c.icon
  return (
    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium ${c.className}`}>
      <Icon />
      {c.label}
    </span>
  )
}
