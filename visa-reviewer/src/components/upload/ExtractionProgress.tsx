interface Props {
  status: string | null
}

export default function ExtractionProgress({ status }: Props) {
  const messages: Record<string, string> = {
    starting: '抽出を開始しています...',
    queued: '実行待ち...',
    running: '書類からデータを抽出中...',
    completed: '抽出完了！リダイレクト中...',
    needs_review: '抽出完了！レビュー画面に移動します...',
    failed: '抽出に失敗しました。もう一度お試しください。',
  }

  const isActive = status && !['completed', 'needs_review', 'failed'].includes(status)

  return (
    <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
      <div className="flex items-center gap-3">
        {isActive && (
          <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
        )}
        <p className="text-sm text-blue-800">
          {messages[status ?? ''] ?? `Status: ${status}`}
        </p>
      </div>
    </div>
  )
}
