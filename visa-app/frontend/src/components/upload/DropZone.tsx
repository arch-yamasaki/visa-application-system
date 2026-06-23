import { useCallback, useState } from 'react'

const IGNORED_NAMES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '.gitkeep'])
const SUPPORTED_EXTENSIONS = new Set(['pdf', 'docx', 'xlsx', 'png', 'jpg', 'jpeg'])

function extension(fileName: string): string {
  return fileName.includes('.') ? fileName.split('.').pop()?.toLowerCase() ?? '' : ''
}

function partitionFiles(files: File[]): { accepted: File[]; rejected: File[] } {
  const filtered = files.filter(
    (f) => f.size > 0 && !IGNORED_NAMES.has(f.name) && !f.name.startsWith('._'),
  )
  return {
    accepted: filtered.filter((file) => SUPPORTED_EXTENSIONS.has(extension(file.name))),
    rejected: filtered.filter((file) => !SUPPORTED_EXTENSIONS.has(extension(file.name))),
  }
}

interface Props {
  onFilesSelected: (files: File[]) => void
  disabled?: boolean
}

export default function DropZone({ onFilesSelected, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false)
  const [rejectedCount, setRejectedCount] = useState(0)

  const selectFiles = useCallback((files: File[]) => {
    const { accepted, rejected } = partitionFiles(files)
    setRejectedCount(rejected.length)
    if (accepted.length > 0) onFilesSelected(accepted)
  }, [onFilesSelected])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      if (disabled) return
      selectFiles(Array.from(e.dataTransfer.files))
    },
    [selectFiles, disabled],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      selectFiles(Array.from(e.target.files ?? []))
      e.target.value = ''
    },
    [selectFiles],
  )

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`
        border-2 border-dashed rounded-xl p-10 text-center transition-colors
        ${dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 bg-white'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-blue-300'}
      `}
    >
      <p className="text-gray-500 mb-2">
        ここにファイルをドラッグ＆ドロップ
      </p>
      <p className="text-sm text-gray-400 mb-3">
        PDF、Excel（.xlsx）、Word（.docx）、画像（.png/.jpg/.jpeg）
      </p>
      {rejectedCount > 0 && (
        <p className="text-sm text-red-600 mb-3">
          未対応のファイルを{rejectedCount}件スキップしました。
        </p>
      )}
      <div className="flex justify-center gap-3">
        <label className={`inline-block px-4 py-2 rounded-lg text-sm font-medium ${
          disabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-blue-50 text-blue-600 cursor-pointer hover:bg-blue-100'
        }`}>
          ファイルを選択
          <input
            type="file"
            multiple
            accept=".pdf,.xlsx,.docx,.png,.jpg,.jpeg"
            onChange={handleChange}
            disabled={disabled}
            className="hidden"
          />
        </label>
        <label className={`inline-block px-4 py-2 rounded-lg text-sm font-medium ${
          disabled
            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
            : 'bg-green-50 text-green-600 cursor-pointer hover:bg-green-100'
        }`}>
          フォルダを選択
          <input
            type="file"
            // @ts-expect-error webkitdirectory is not in React's type defs
            webkitdirectory=""
            accept=".pdf,.xlsx,.docx,.png,.jpg,.jpeg"
            onChange={handleChange}
            disabled={disabled}
            className="hidden"
          />
        </label>
      </div>
    </div>
  )
}
