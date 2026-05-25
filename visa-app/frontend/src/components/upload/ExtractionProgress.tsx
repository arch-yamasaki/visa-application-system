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
  if (error.includes('RESOURCE_EXHAUSTED') || error.includes('429')) {
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

  if (event === 'complete' || (info && event === 'progress' && isCompleted(phase, info))) {
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

/** フェーズが「後続フェーズが始まっている」ため完了扱いかを判定 */
function isCompleted(_phase: string, _info: PhaseInfo): boolean {
  return false
}

function resolvePhaseStatus(
  phases: Record<string, PhaseInfo>,
): Record<string, PhaseInfo | undefined> {
  const result: Record<string, PhaseInfo | undefined> = {}
  let foundActive = false

  // 逆順で走査して、アクティブフェーズより前は完了扱いにする
  for (const phase of PHASE_ORDER) {
    result[phase] = phases[phase]
  }

  // アクティブなフェーズを見つけ、それ以前のフェーズを完了扱いに
  for (const phase of PHASE_ORDER) {
    if (phases[phase]?.event === 'progress') {
      foundActive = true
      break
    }
  }

  if (foundActive) {
    for (const phase of PHASE_ORDER) {
      if (phases[phase]?.event === 'progress') break
      if (!result[phase]) {
        result[phase] = { event: 'complete', message: PHASE_LABELS[phase] }
      } else if (result[phase]?.event === 'progress') {
        break
      }
    }
  }

  return result
}

export default function ExtractionProgress({ phases, status, error }: Props) {
  // SSE フェーズ表示（Gemini用）
  if (phases && Object.keys(phases).length > 0) {
    const resolved = resolvePhaseStatus(phases)

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
