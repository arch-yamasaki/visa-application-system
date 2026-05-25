import { useEffect, useState } from 'react'

type CopyStatus = 'copied' | 'error' | null

interface Props {
  caseId: string
  className?: string
  feedbackClassName?: string
  stopPropagation?: boolean
}

export default function CopyableCaseId({
  caseId,
  className,
  feedbackClassName,
  stopPropagation = false,
}: Props) {
  const [status, setStatus] = useState<CopyStatus>(null)

  useEffect(() => {
    if (!status) return
    const timer = window.setTimeout(() => setStatus(null), 1800)
    return () => window.clearTimeout(timer)
  }, [status])

  const handleCopy = async (event: React.MouseEvent<HTMLButtonElement>) => {
    if (stopPropagation) {
      event.stopPropagation()
    }

    try {
      await navigator.clipboard.writeText(caseId)
      setStatus('copied')
    } catch {
      setStatus('error')
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={handleCopy}
        className={`font-mono transition-colors hover:text-blue-600 cursor-copy ${className ?? ''}`}
        aria-label={`${caseId} をコピー`}
        title={caseId}
      >
        {caseId}
      </button>
      {status && (
        <span
          className={`text-[11px] ${status === 'copied' ? 'text-green-600' : 'text-red-500'} ${feedbackClassName ?? ''}`}
        >
          {status === 'copied' ? 'コピー済' : '失敗'}
        </span>
      )}
    </span>
  )
}
