import { useId, useMemo, useState } from 'react'
import type { CaseData, FieldMetadataMap } from '../../types/caseData'
import { getByPath, getFieldInput, getFieldLabel } from '../../lib/fieldPaths'
import FieldRow from './FieldRow'

interface RepeatedField {
  path: string
}

interface Props {
  title: string
  itemLabel: string
  basePath: string
  maxItems: number
  fields: RepeatedField[]
  enabled: boolean
  caseData: CaseData
  fieldMetadata: FieldMetadataMap
  onFieldUpdate: (fieldPath: string, value: string) => void
}

function hasItemValue(caseData: CaseData, basePath: string, index: number, fields: RepeatedField[]) {
  return fields.some((field) => {
    const value = getByPath(caseData, `${basePath}.${index}.${field.path}`)
    return value !== null && value !== undefined && value !== ''
  })
}

export default function RepeatedFieldGroup({
  title,
  itemLabel,
  basePath,
  maxItems,
  fields,
  enabled,
  caseData,
  fieldMetadata,
  onFieldUpdate,
}: Props) {
  const contentId = useId()
  const filledCount = useMemo(() => {
    let count = 0
    for (let index = 0; index < maxItems; index += 1) {
      if (hasItemValue(caseData, basePath, index, fields)) count += 1
    }
    return count
  }, [basePath, caseData, fields, maxItems])
  const [open, setOpen] = useState(filledCount > 0)
  const [itemCount, setItemCount] = useState(Math.max(1, filledCount))
  const visibleCount = Math.min(maxItems, Math.max(itemCount, filledCount))

  const addItem = () => {
    if (!enabled) return
    setOpen(true)
    setItemCount((current) => Math.min(maxItems, current + 1))
  }

  const clearItem = (index: number) => {
    if (!enabled) return
    for (const field of fields) {
      onFieldUpdate(`${basePath}.${index}.${field.path}`, '')
    }
  }

  return (
    <div className="border-y border-gray-100 bg-gray-50/70">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-inset"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => {
          if (enabled || filledCount > 0) setOpen((current) => !current)
        }}
      >
        <span className="font-medium text-gray-700">{title}</span>
        <span className="text-xs text-gray-500">
          {enabled ? `${filledCount}/${maxItems}件` : '有にすると入力できます'}
        </span>
      </button>

      {open && enabled && (
        <div id={contentId} className="pb-2">
          {Array.from({ length: visibleCount }, (_, index) => (
            <div key={`${basePath}.${index}`} className="mx-2 mb-2 border border-gray-200 bg-white">
              <div className="flex items-center justify-between border-b border-gray-100 px-3 py-1.5">
                <span className="text-xs font-medium text-gray-500">
                  {itemLabel} {index + 1}
                </span>
                <button
                  type="button"
                  className="text-xs text-gray-400 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                  onClick={() => clearItem(index)}
                >
                  クリア
                </button>
              </div>
              {fields.map((field) => {
                const path = `${basePath}.${index}.${field.path}`
                return (
                  <FieldRow
                    key={path}
                    label={getFieldLabel(path)}
                    fieldPath={path}
                    value={getByPath(caseData, path)}
                    input={getFieldInput(path)}
                    meta={fieldMetadata[path]}
                    onUpdate={onFieldUpdate}
                  />
                )
              })}
            </div>
          ))}

          <button
            type="button"
            className="ml-3 rounded border border-blue-200 px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:border-gray-200 disabled:text-gray-300 disabled:hover:bg-transparent"
            disabled={visibleCount >= maxItems}
            onClick={addItem}
          >
            追加
          </button>
        </div>
      )}
    </div>
  )
}
