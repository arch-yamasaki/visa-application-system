interface Props {
  status: string | null
}

export default function ExtractionProgress({ status }: Props) {
  const messages: Record<string, string> = {
    starting: 'Starting extraction...',
    queued: 'Queued, waiting for runner...',
    running: 'Codex is extracting data from documents...',
    completed: 'Extraction complete! Redirecting...',
    needs_review: 'Extraction complete! Redirecting to review...',
    failed: 'Extraction failed. Please try again.',
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
