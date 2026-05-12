import { useState } from 'react'
import type { FieldMeta } from '../../types/caseData'
import { useViewerStore } from '../../store/viewerStore'
import FlagBadge from './FlagBadge'

interface Props {
  label: string
  fieldPath: string
  value: unknown
  meta?: FieldMeta
  flagType?: 'ok' | 'needs_review' | 'missing' | 'error' | 'edited'
  onUpdate?: (fieldPath: string, value: string) => void
}

export default function FieldRow({ label, fieldPath, value, meta, flagType, onUpdate }: Props) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const navigateToSource = useViewerStore((s) => s.navigateToSource)

  const displayValue = value === null || value === undefined || value === '' ? '(empty)' : String(value)
  const confidence = meta?.source_refs?.[0]?.confidence
  const hasSource = meta?.source_refs && meta.source_refs.length > 0

  const handleClick = () => {
    if (hasSource && meta?.source_refs?.[0]) {
      navigateToSource(meta.source_refs[0])
    }
  }

  const handleDoubleClick = () => {
    if (!onUpdate) return
    setEditValue(displayValue === '(empty)' ? '' : displayValue)
    setEditing(true)
  }

  const handleSave = () => {
    onUpdate?.(fieldPath, editValue)
    setEditing(false)
  }

  const badgeType = meta?.human_edited ? 'edited' : flagType ?? 'ok'

  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 hover:bg-blue-50 cursor-pointer text-sm group ${
        hasSource ? '' : 'opacity-70'
      }`}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      <span className="w-40 shrink-0 text-gray-500 truncate text-xs">{label}</span>

      {editing ? (
        <div className="flex-1 flex gap-1">
          <input
            className="flex-1 px-2 py-0.5 border border-blue-300 rounded text-sm"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            autoFocus
          />
          <button
            onClick={(e) => { e.stopPropagation(); handleSave() }}
            className="px-2 py-0.5 bg-blue-600 text-white rounded text-xs"
          >
            Save
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setEditing(false) }}
            className="px-2 py-0.5 text-gray-500 text-xs"
          >
            Cancel
          </button>
        </div>
      ) : (
        <span className={`flex-1 truncate ${displayValue === '(empty)' ? 'text-gray-300 italic' : 'text-gray-800'}`}>
          {displayValue}
        </span>
      )}

      {confidence !== undefined && (
        <span
          className={`text-[10px] font-mono ${
            confidence >= 0.9 ? 'text-green-600' : confidence >= 0.7 ? 'text-yellow-600' : 'text-red-500'
          }`}
        >
          {Math.round(confidence * 100)}%
        </span>
      )}

      <FlagBadge type={badgeType} />

      {hasSource && (
        <span className="text-[10px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
          p.{meta?.source_refs?.[0]?.page}
        </span>
      )}
    </div>
  )
}
