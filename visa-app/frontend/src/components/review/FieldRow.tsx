import { useRef, useState } from 'react'
import type { FieldMeta } from '../../types/caseData'
import { getDisplayValue, type FieldInput } from '../../lib/fieldPaths'
import { useViewerStore } from '../../store/viewerStore'

interface Props {
  label: string
  fieldPath: string
  value: unknown
  input: FieldInput
  meta?: FieldMeta
  onUpdate?: (fieldPath: string, value: string) => void
}

function normalizeEditorValue(value: string, type: FieldInput['type']): string {
  if (type === 'select') return normalizeChoiceValue(value)
  if (type === 'number') return value.replace(/\D/g, '')
  if (type === 'date') return toDateValue(value)
  if (type === 'month' && /^\d{4}-\d{2}/.test(value)) {
    return value.slice(0, 7)
  }
  if (type === 'month') return toMonthValue(value)
  return value
}

export default function FieldRow({ label, fieldPath, value, input, meta, onUpdate }: Props) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const navigateToSource = useViewerStore((s) => s.navigateToSource)
  const activeFieldPath = useViewerStore((s) => s.activeFieldPath)
  const setActiveFieldPath = useViewerStore((s) => s.setActiveFieldPath)
  const rowRef = useRef<HTMLDivElement>(null)

  const rawValue = value === null || value === undefined || value === '' ? '' : String(value)
  const displayValue = rawValue === '' ? '(未入力)' : getDisplayValue(rawValue) || rawValue
  const hasSource = meta?.source_refs && meta.source_refs.length > 0
  const isActive = activeFieldPath === fieldPath
  const inputOptions = input.options ?? []
  const selectOptions = input.type === 'select' && rawValue !== '' && !inputOptions.some((option) => option.value === rawValue)
    ? [...inputOptions, { value: rawValue, label: getDisplayValue(rawValue) || rawValue }]
    : inputOptions

  const handleClick = () => {
    setActiveFieldPath(fieldPath)
    if (hasSource && meta?.source_refs?.[0]) {
      navigateToSource(meta.source_refs[0])
    }
  }

  const startEditing = () => {
    if (!onUpdate) return
    setEditValue(normalizeEditorValue(rawValue, input.type))
    setEditing(true)
  }

  const handleSave = () => {
    onUpdate?.(fieldPath, editValue)
    setEditing(false)
  }

  const handleInputChange = (value: string) => {
    setEditValue(input.type === 'number' ? value.replace(/\D/g, '') : value)
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

  return (
    <div
      ref={rowRef}
      data-field-row
      tabIndex={0}
      role="button"
      aria-selected={isActive}
      className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer text-sm group outline-none transition-colors ${
        isActive
          ? 'bg-blue-100 border-l-2 border-blue-500'
          : 'hover:bg-blue-50'
      } focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-inset`}
      onClick={handleClick}
      onDoubleClick={startEditing}
      onKeyDown={handleKeyDown}
      title={hasSource ? 'クリックで証跡を表示' : undefined}
    >
      <span className="w-44 shrink-0 text-gray-500 truncate text-xs">{label}</span>

      {editing ? (
        <div
          className="flex-1 flex gap-1"
          onClick={(e) => e.stopPropagation()}
          onDoubleClick={(e) => e.stopPropagation()}
        >
          {input.type === 'select' ? (
            <select
              className="flex-1 px-2 py-0.5 border border-blue-300 rounded text-sm bg-white focus:outline-none focus:ring-1 focus:ring-blue-400"
              value={editValue}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSave()
                if (e.key === 'Escape') handleCancel()
                e.stopPropagation()
              }}
              autoFocus
            >
              <option value="">(未入力)</option>
              {selectOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="flex-1 px-2 py-0.5 border border-blue-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              type={input.type === 'number' ? 'text' : input.type}
              inputMode={input.type === 'number' ? 'numeric' : undefined}
              pattern={input.type === 'number' ? '[0-9]*' : undefined}
              value={editValue}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSave()
                if (e.key === 'Escape') handleCancel()
                e.stopPropagation()
              }}
              autoFocus
            />
          )}
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

      {hasSource && (
        <span className="text-xs text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
          p.{meta?.source_refs?.[0]?.page}
        </span>
      )}
    </div>
  )
}

function normalizeChoiceValue(value: string): string {
  const normalized = value.trim().toLowerCase()
  if (['true', 'yes', '有', 'あり', '有 yes', '1'].includes(normalized)) return 'true'
  if (['false', 'no', '無', 'なし', '無 no', '0'].includes(normalized)) return 'false'
  if (normalized === 'single') return 'single'
  if (normalized === 'unmarried') return 'unmarried'
  if (normalized === 'married') return 'married'
  return value
}

function toDateValue(value: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const digits = value.replace(/\D/g, '')
  if (digits.length >= 8) {
    return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`
  }
  return ''
}

function toMonthValue(value: string): string {
  if (/^\d{4}-\d{2}$/.test(value)) return value
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.slice(0, 7)
  const digits = value.replace(/\D/g, '')
  if (digits.length >= 6) {
    return `${digits.slice(0, 4)}-${digits.slice(4, 6)}`
  }
  return ''
}
