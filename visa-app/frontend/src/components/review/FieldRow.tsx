import { useId, useRef, useState, type ReactNode } from 'react'
import type { FieldAlternative, FieldMeta, SourceRef } from '../../types/caseData'
import { getDisplayValue, type FieldInput } from '../../lib/fieldPaths'
import { useViewerStore } from '../../store/viewerStore'

interface Props {
  label: string
  fieldPath: string
  value: unknown
  input: FieldInput
  meta?: FieldMeta
  onUpdate?: (fieldPath: string, value: string) => void
  readOnly?: boolean
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

function pickPrimarySourceRef(sourceRefs: SourceRef[] | undefined): SourceRef | undefined {
  if (!sourceRefs?.length) return undefined
  return (
    sourceRefs.find((ref) => ref.anchor?.status === 'resolved')
    ?? sourceRefs.find((ref) => ref.bbox)
    ?? sourceRefs.find((ref) => !ref.anchor)
    ?? sourceRefs[0]
  )
}

function truncateText(value: string, maxLength = 40): string {
  if (value.length <= maxLength) return value
  return `${value.slice(0, maxLength)}...`
}

export default function FieldRow({ label, fieldPath, value, input, meta, onUpdate, readOnly = false }: Props) {
  const alternativesId = useId()
  const [editing, setEditing] = useState(false)
  const [alternativesOpen, setAlternativesOpen] = useState(false)
  const [editValue, setEditValue] = useState('')
  const navigateToSource = useViewerStore((s) => s.navigateToSource)
  const activeFieldPath = useViewerStore((s) => s.activeFieldPath)
  const setActiveFieldPath = useViewerStore((s) => s.setActiveFieldPath)
  const documents = useViewerStore((s) => s.documents)
  const rowRef = useRef<HTMLDivElement>(null)

  const rawValue = value === null || value === undefined || value === '' ? '' : String(value)
  const displayValue = rawValue === '' ? '(未入力)' : getDisplayValue(rawValue) || rawValue
  const primarySourceRef = pickPrimarySourceRef(meta?.source_refs)
  const hasSource = Boolean(primarySourceRef)
  const positionCandidateCount =
    primarySourceRef?.anchor?.status === 'ambiguous'
      ? primarySourceRef.anchor.candidates?.length ?? 0
      : 0
  const alternatives = meta?.alternatives?.filter((alternative) => alternative.source_refs?.length) ?? []
  const hasAlternatives = alternatives.length > 0
  const isActive = activeFieldPath === fieldPath
  const inputOptions = input.options ?? []
  const selectOptions = input.type === 'select' && rawValue !== '' && !inputOptions.some((option) => option.value === rawValue)
    ? [...inputOptions, { value: rawValue, label: getDisplayValue(rawValue) || rawValue }]
    : inputOptions

  const handleClick = () => {
    setActiveFieldPath(fieldPath)
    if (primarySourceRef) {
      navigateToSource(primarySourceRef)
    }
  }

  const startEditing = () => {
    if (readOnly || !onUpdate) return
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

  const documentName = (ref: SourceRef | undefined): string => {
    if (!ref) return '書類不明'
    return documents.find((doc) => doc.document_id === ref.document_id)?.file_name
      ?? ref.document_id
      ?? '書類不明'
  }

  const sourceLine = (ref: SourceRef | undefined): string => {
    if (!ref) return '証跡なし'
    const page = ref.page ? `p.${ref.page}` : 'p.-'
    return `${documentName(ref)} / ${page}`
  }

  const handleAlternativeNavigate = (ref: SourceRef | undefined) => {
    if (!ref) return
    setActiveFieldPath(fieldPath)
    navigateToSource(ref)
  }

  const handleAdopt = (alternative: FieldAlternative) => {
    onUpdate?.(fieldPath, String(alternative.value))
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
    <div>
      <div
        ref={rowRef}
        data-field-row
        data-read-only={readOnly || undefined}
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

        {positionCandidateCount > 1 && (
          <span
            className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-300"
            title="証跡の位置が複数見つかっています。PDFビューアで候補を確認できます"
          >
            位置候補{positionCandidateCount}
          </span>
        )}

        {readOnly && (
          <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
            固定設定
          </span>
        )}
        {hasAlternatives && (
          <button
            type="button"
            className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300"
            aria-expanded={alternativesOpen}
            aria-controls={alternativesId}
            title="値が食い違う別候補があります"
            onClick={(e) => {
              e.stopPropagation()
              setAlternativesOpen((current) => !current)
            }}
          >
            別候補{alternatives.length}
          </button>
        )}
        {hasSource && (
          <span className="text-xs text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
            p.{primarySourceRef?.page}
          </span>
        )}
      </div>

      {alternativesOpen && hasAlternatives && (
        <div
          id={alternativesId}
          className="border-t border-rose-100 bg-rose-50/40 px-3 py-2 text-xs"
          onClick={(e) => e.stopPropagation()}
        >
          <EvidenceOption
            label="現在の値"
            value={displayValue}
            sourceLine={sourceLine(primarySourceRef)}
            quote={primarySourceRef?.text_quote}
            onNavigate={() => handleAlternativeNavigate(primarySourceRef)}
          />
          {alternatives.map((alternative, index) => {
            const ref = pickPrimarySourceRef(alternative.source_refs)
            const altValue = getDisplayValue(String(alternative.value)) || String(alternative.value)
            const isCurrent = String(alternative.value) === rawValue
            return (
              <EvidenceOption
                key={`${fieldPath}-alternative-${index}`}
                label={`別候補 ${index + 1}`}
                value={altValue}
                sourceLine={sourceLine(ref)}
                quote={ref?.text_quote}
                onNavigate={() => handleAlternativeNavigate(ref)}
                action={onUpdate && !readOnly ? (
                  <button
                    type="button"
                    className="shrink-0 rounded border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50 disabled:text-gray-400 disabled:hover:bg-white"
                    disabled={isCurrent}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleAdopt(alternative)
                    }}
                  >
                    {isCurrent ? '採用中' : '採用'}
                  </button>
                ) : undefined}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

interface EvidenceOptionProps {
  label: string
  value: string
  sourceLine: string
  quote?: string
  onNavigate: () => void
  action?: ReactNode
}

function EvidenceOption({ label, value, sourceLine, quote, onNavigate, action }: EvidenceOptionProps) {
  return (
    <div className="flex items-start gap-2 py-1.5">
      <button
        type="button"
        className="min-w-0 flex-1 text-left hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300"
        onClick={onNavigate}
      >
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="font-medium text-rose-700">{label}</span>
          <span className="font-medium text-gray-900 break-all">{value}</span>
          <span className="text-gray-500">{sourceLine}</span>
        </div>
        {quote && (
          <div className="mt-0.5 text-gray-500 break-all">
            {truncateText(quote)}
          </div>
        )}
      </button>
      {action}
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
