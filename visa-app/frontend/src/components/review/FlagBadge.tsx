interface Props {
  type: 'action_needed' | 'edited'
}

const WarningIcon = () => (
  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="inline-block">
    <path d="M8 1L15 14H1L8 1Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M8 6V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="8" cy="11.5" r="0.75" fill="currentColor" />
  </svg>
)

const EditIcon = () => (
  <svg width="10" height="10" viewBox="0 0 16 16" fill="none" className="inline-block">
    <path d="M11 2L14 5L5 14H2V11L11 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
  </svg>
)

const config: Record<string, { label: string; className: string; icon: React.FC }> = {
  action_needed: { label: '要対応', className: 'bg-orange-100 text-orange-700', icon: WarningIcon },
  edited: { label: '編集済', className: 'bg-blue-100 text-blue-700', icon: EditIcon },
}

export default function FlagBadge({ type }: Props) {
  const c = config[type]
  const Icon = c.icon
  return (
    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium ${c.className}`}>
      <Icon />
      {c.label}
    </span>
  )
}
