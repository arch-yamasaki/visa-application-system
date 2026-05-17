import { useRef, useState } from 'react'
import type { FieldMeta } from '../../types/caseData'
import { useViewerStore } from '../../store/viewerStore'
import { getDisplayValue } from '../../lib/fieldPaths'
import FlagBadge from './FlagBadge'

interface Props {
  label: string
  fieldPath: string
  value: unknown
  meta?: FieldMeta
  flagType?: 'ok' | 'needs_review' | 'missing' | 'error' | 'edited'
  onUpdate?: (fieldPath: string, value: string) => void
}

function ConfidenceDots({ confidence }: { confidence: number }) {
  const filled = Math.round(confidence * 5)
  const color = confidence >= 0.9 ? 'bg-green-500' : confidence >= 0.7 ? 'bg-yellow-500' : 'bg-red-400'
  return (
    <div className="flex items-center gap-px" title={`${Math.round(confidence * 100)}%`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={`block w-1.5 h-1.5 rounded-full ${i < filled ? color : 'bg-gray-200'}`}
        />
      ))}
    </div>
  )
}

export default function FieldRow({ label, fieldPath, value, meta, flagType, onUpdate }: Props) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const navigateToSource = useViewerStore((s) => s.navigateToSource)
  const activeFieldPath = useViewerStore((s) => s.activeFieldPath)
  const setActiveFieldPath = useViewerStore((s) => s.setActiveFieldPath)
  const rowRef = useRef<HTMLDivElement>(null)

  const rawValue = value === null || value === undefined || value === '' ? '' : String(value)
  const displayValue = rawValue === '' ? '(未入力)' : getDisplayValue(rawValue) || rawValue
  const confidence = meta?.source_refs?.[0]?.confidence
  const hasSource = meta?.source_refs && meta.source_refs.length > 0
  const isActive = activeFieldPath === fieldPath
  const isEdited = meta?.human_edited

  const handleClick = () => {
    setActiveFieldPath(fieldPath)
    if (hasSource && meta?.source_refs?.[0]) {
      navigateToSource(meta.source_refs[0])
    }
  }

  const startEditing = () => {
    if (!onUpdate) return
    setEditValue(displayValue === '(未入力)' ? '' : displayValue)
    setEditing(true)
  }

  const handleSave = () => {
    onUpdate?.(fieldPath, editValue)
    setEditing(false)
  }

  const handleCancel = () => {
    setEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (editing) {
      if (e.key === 'Escape') {
        e.preventDefault()
        handleCancel()
      }
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      startEditing()
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const rows = Array.from(
        rowRef.current?.closest('[data-field-panel]')?.querySelectorAll('[data-field-row]') ?? [],
      ) as HTMLElement[]
      const idx = rows.indexOf(rowRef.current!)
      const next = e.key === 'ArrowDown' ? rows[idx + 1] : rows[idx - 1]
      next?.focus()
    }
  }

  const badgeType = meta?.human_edited ? 'edited' : flagType ?? 'ok'

  return (
    <div
      ref={rowRef}
      data-field-row
      tabIndex={0}
      className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer text-sm group outline-none transition-colors ${
        isActive
          ? 'bg-blue-100 border-l-2 border-blue-500'
          : isEdited
            ? 'bg-sky-50 hover:bg-blue-50'
            : 'hover:bg-blue-50'
      } ${hasSource ? '' : 'opacity-70'} focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-inset`}
      onClick={handleClick}
      onDoubleClick={startEditing}
      onKeyDown={handleKeyDown}
      title={hasSource ? 'クリックで証跡を表示' : undefined}
    >
      <span className="w-44 shrink-0 text-gray-500 truncate text-xs">{label}</span>

      {editing ? (
        <div className="flex-1 flex gap-1">
          <input
            className="flex-1 px-2 py-0.5 border border-blue-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave()
              if (e.key === 'Escape') handleCancel()
              e.stopPropagation()
            }}
            autoFocus
          />
          <button
            onClick={(e) => { e.stopPropagation(); handleSave() }}
            className="px-2 py-0.5 bg-blue-600 text-white rounded text-xs"
          >
            保存
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); handleCancel() }}
            className="px-2 py-0.5 text-gray-500 text-xs hover:text-gray-700"
          >
            取消
          </button>
        </div>
      ) : (
        <span className={`flex-1 truncate ${displayValue === '(未入力)' ? 'text-gray-300 italic' : 'text-gray-800'}`}>
          {displayValue}
        </span>
      )}

      {confidence !== undefined && <ConfidenceDots confidence={confidence} />}

      <FlagBadge type={badgeType} />

      {hasSource ? (
        <span className="text-[10px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
          p.{meta?.source_refs?.[0]?.page}
        </span>
      ) : (
        <span className="text-[10px] text-gray-300 italic">(証跡なし)</span>
      )}
    </div>
  )
}
