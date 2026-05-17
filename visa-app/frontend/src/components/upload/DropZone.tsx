import { useCallback, useState } from 'react'

const IGNORED_NAMES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini', '.gitkeep'])

function filterFiles(files: File[]): File[] {
  return files.filter(
    (f) => f.size > 0 && !IGNORED_NAMES.has(f.name) && !f.name.startsWith('._'),
  )
}

interface Props {
  onFilesSelected: (files: File[]) => void
  disabled?: boolean
}

export default function DropZone({ onFilesSelected, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      if (disabled) return
      const files = filterFiles(Array.from(e.dataTransfer.files))
      if (files.length > 0) onFilesSelected(files)
    },
    [onFilesSelected, disabled],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = filterFiles(Array.from(e.target.files ?? []))
      if (files.length > 0) onFilesSelected(files)
      e.target.value = ''
    },
    [onFilesSelected],
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
        PDF、Excel、Word、画像ファイル
      </p>
      <div className="flex justify-center gap-3">
        <label className="inline-block px-4 py-2 bg-blue-50 text-blue-600 rounded-lg text-sm font-medium cursor-pointer hover:bg-blue-100">
          ファイルを選択
          <input
            type="file"
            multiple
            accept=".pdf,.xlsx,.xls,.doc,.docx,.png,.jpg,.jpeg,.tiff,.tif"
            onChange={handleChange}
            disabled={disabled}
            className="hidden"
          />
        </label>
        <label className="inline-block px-4 py-2 bg-green-50 text-green-600 rounded-lg text-sm font-medium cursor-pointer hover:bg-green-100">
          フォルダを選択
          <input
            type="file"
            // @ts-expect-error webkitdirectory is not in React's type defs
            webkitdirectory=""
            onChange={handleChange}
            disabled={disabled}
            className="hidden"
          />
        </label>
      </div>
    </div>
  )
}
