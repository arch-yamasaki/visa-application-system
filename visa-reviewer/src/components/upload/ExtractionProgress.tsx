import { useEffect, useState } from 'react'

interface Props {
  status: string | null
  backend?: string
}

const steps = [
  '書類を読み込んでいます...',
  'テキストを解析しています...',
  'データを構造化しています...',
  '整合性を確認しています...',
  'レビュー項目を生成しています...',
]

export default function ExtractionProgress({ status, backend }: Props) {
  const [stepIndex, setStepIndex] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (status === 'failed') return
    const timer = setInterval(() => {
      setElapsed((prev) => prev + 1)
      setStepIndex((prev) => (prev < steps.length - 1 ? prev + 1 : prev))
    }, 3000)
    return () => clearInterval(timer)
  }, [status])

  const isFailed = status === 'failed'
  const isDone = status === 'completed' || status === 'needs_review'

  const message = isFailed
    ? '抽出に失敗しました。もう一度お試しください。'
    : isDone
      ? '抽出完了！レビュー画面に移動します...'
      : backend === 'codex'
        ? { starting: '抽出を開始しています...', queued: '実行待ち...', running: '書類からデータを抽出中...' }[status ?? ''] ?? steps[stepIndex]
        : steps[stepIndex]

  return (
    <div className={`mt-6 p-5 rounded-lg border ${isFailed ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200'}`}>
      <div className="flex items-center gap-3 mb-3">
        {!isFailed && !isDone && (
          <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin shrink-0" />
        )}
        {isDone && (
          <svg width="20" height="20" viewBox="0 0 20 20" className="text-green-500 shrink-0">
            <circle cx="10" cy="10" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M6 10l3 3 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        <p className={`text-sm font-medium ${isFailed ? 'text-red-700' : 'text-blue-800'}`}>
          {message}
        </p>
      </div>

      {!isFailed && !isDone && (
        <>
          <div className="flex gap-1 mb-2">
            {steps.map((_, i) => (
              <div
                key={i}
                className={`h-1 flex-1 rounded-full transition-colors duration-500 ${
                  i <= stepIndex ? 'bg-blue-400' : 'bg-blue-200'
                }`}
              />
            ))}
          </div>
          <p className="text-xs text-blue-500">
            {elapsed > 0 && `${elapsed}秒経過`}
            {backend !== 'codex' && elapsed > 10 && ' — 書類が多い場合は少しお待ちください'}
          </p>
        </>
      )}
    </div>
  )
}
