interface Props {
  status: string | null
  backend?: string
}

export default function ExtractionProgress({ status }: Props) {
  const isFailed = status === 'failed'

  return (
    <div className={`mt-6 p-4 rounded-lg border ${isFailed ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200'}`}>
      <div className="flex items-center gap-3">
        {!isFailed && (
          <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin shrink-0" />
        )}
        <p className={`text-sm ${isFailed ? 'text-red-700' : 'text-blue-800'}`}>
          {isFailed ? '抽出に失敗しました。もう一度お試しください。' : '書類からデータを抽出中...'}
        </p>
      </div>
    </div>
  )
}
