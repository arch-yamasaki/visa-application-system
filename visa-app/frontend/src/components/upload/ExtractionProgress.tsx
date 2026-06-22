export interface PhaseInfo {
  event: string
  message?: string
}

interface Props {
  /** SSE フェーズ進捗（Gemini用） */
  phases?: Record<string, PhaseInfo>
  /** レガシー: ステータス文字列（Codex用） */
  status?: string | null
  backend?: string
  error?: string | null
}

function formatErrorMessage(error: string): string {
  if (
    error.includes('漏洩報告済み')
    || error.includes('API key was reported as leaked')
  ) {
    return 'Gemini APIキーが漏洩報告済みのため無効です。管理者がGOOGLE_API_KEYを新しいキーに差し替える必要があります。'
  }
  if (
    error.includes('PERMISSION_DENIED')
    || error.includes('API_KEY_INVALID')
    || error.includes('APIキーが無効')
    || error.includes('権限不足')
  ) {
    return 'Gemini APIキーが無効、または権限不足です。GOOGLE_API_KEYを確認してください。'
  }
  if (
    error.includes('RESOURCE_EXHAUSTED')
    || error.includes('429')
    || error.includes('API利用上限')
  ) {
    return 'API利用上限に達しました。しばらく待ってから再度お試しください。'
  }
  return '抽出に失敗しました。もう一度お試しください。'
}

/** フェーズ定義（表示順） */
const PHASE_ORDER = ['downloading', 'extracting', 'saving'] as const
const PHASE_LABELS: Record<string, string> = {
  downloading: 'ドキュメント読み込み',
  extracting: 'Gemini APIで抽出',
  saving: '保存',
}

function PhaseRow({ phase, info }: { phase: string; info?: PhaseInfo }) {
  const label = PHASE_LABELS[phase] ?? phase
  const event = info?.event

  if (event === 'error') {
    return (
      <div className="flex items-center gap-3 text-red-700">
        <span className="text-base leading-none">!</span>
        <span className="text-sm">{info?.message ?? `${label}に失敗`}</span>
      </div>
    )
  }

  if (event === 'complete') {
    // 完了
    return (
      <div className="flex items-center gap-3 text-green-700">
        <span className="text-base leading-none">&#x2713;</span>
        <span className="text-sm">{info?.message ?? label}</span>
      </div>
    )
  }

  if (event === 'progress') {
    // 実行中
    return (
      <div className="flex items-center gap-3 text-blue-700">
        <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin shrink-0" />
        <span className="text-sm">{info?.message ?? `${label}中...`}</span>
      </div>
    )
  }

  // 未開始
  return (
    <div className="flex items-center gap-3 text-gray-400">
      <span className="text-base leading-none">&#x25CB;</span>
      <span className="text-sm">{label}</span>
    </div>
  )
}

function resolvePhaseStatus(
  phases: Record<string, PhaseInfo>,
): Record<string, PhaseInfo | undefined> {
  const result: Record<string, PhaseInfo | undefined> = {}

  for (const phase of PHASE_ORDER) {
    result[phase] = phases[phase]
  }

  const activeIndex = PHASE_ORDER.findLastIndex(
    (phase) => phases[phase]?.event === 'progress',
  )

  for (let index = 0; index < activeIndex; index += 1) {
    const phase = PHASE_ORDER[index]
    result[phase] = {
      event: 'complete',
      message: PHASE_LABELS[phase],
    }
  }

  return result
}

export default function ExtractionProgress({ phases, status, error }: Props) {
  // SSE フェーズ表示（Gemini用）
  if (phases && Object.keys(phases).length > 0) {
    const resolved = resolvePhaseStatus(phases)
    if (error) {
      const activePhase = [...PHASE_ORDER]
        .reverse()
        .find((phase) => resolved[phase]?.event === 'progress')
      if (activePhase) {
        resolved[activePhase] = {
          event: 'error',
          message: `${PHASE_LABELS[activePhase]}に失敗`,
        }
      }
    }

    return (
      <div className={`mt-6 p-4 rounded-lg border ${error ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200'}`}>
        <div className="flex flex-col gap-2">
          {PHASE_ORDER.map((phase) => (
            <PhaseRow key={phase} phase={phase} info={resolved[phase]} />
          ))}
        </div>
        {error && (
          <p className="mt-3 text-sm text-red-700">{formatErrorMessage(error)}</p>
        )}
      </div>
    )
  }

  // レガシー表示（Codex用）
  const isFailed = status === 'failed'

  return (
    <div className={`mt-6 p-4 rounded-lg border ${isFailed ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200'}`}>
      <div className="flex items-center gap-3">
        {!isFailed && (
          <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin shrink-0" />
        )}
        <p className={`text-sm ${isFailed ? 'text-red-700' : 'text-blue-800'}`}>
          {isFailed
            ? (error ? formatErrorMessage(error) : '抽出に失敗しました。もう一度お試しください。')
            : '書類からデータを抽出中...'}
        </p>
      </div>
    </div>
  )
}
