interface Props {
  type: 'ok' | 'needs_review' | 'missing' | 'error' | 'edited'
}

const config: Record<string, { label: string; className: string }> = {
  ok: { label: 'OK', className: 'bg-green-100 text-green-700' },
  needs_review: { label: 'Review', className: 'bg-orange-100 text-orange-700' },
  missing: { label: 'Missing', className: 'bg-red-100 text-red-700' },
  error: { label: 'Error', className: 'bg-red-100 text-red-700' },
  edited: { label: 'Edited', className: 'bg-blue-100 text-blue-700' },
}

export default function FlagBadge({ type }: Props) {
  const c = config[type] ?? config.ok
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${c.className}`}>
      {c.label}
    </span>
  )
}
