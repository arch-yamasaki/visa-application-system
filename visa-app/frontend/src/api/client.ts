import type { CaseDocument, CaseSummary, DocumentEntry } from '../types/caseData'
import { mockApi } from './mockData'

const BASE = '/api'

function isDemoMode(): boolean {
  if (import.meta.env.VITE_DEMO === 'true') return true
  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search)
    if (params.get('demo') === 'true') {
      sessionStorage.setItem('visa_demo_mode', 'true')
      return true
    }
    if (sessionStorage.getItem('visa_demo_mode') === 'true') {
      return true
    }
  }
  return false
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

export const apiClient = {
  // Cases
  createCase(params: { application_type: string; target_status: string }) {
    if (isDemoMode()) return mockApi.createCase(params)
    return request<{ case_id: string; workflow_state: string; created_at: string }>(
      '/cases',
      { method: 'POST', body: JSON.stringify(params) },
    )
  },

  listCases(): Promise<CaseSummary[]> {
    if (isDemoMode()) return mockApi.listCases()
    return request('/cases')
  },

  getCase(caseId: string): Promise<CaseDocument> {
    if (isDemoMode()) return mockApi.getCase(caseId)
    return request(`/cases/${caseId}`)
  },

  updateCase(
    caseId: string,
    updates: { case_data?: unknown; settings?: unknown; field_metadata?: unknown; workflow_state?: string },
  ) {
    if (isDemoMode()) return mockApi.updateCase(caseId, updates)
    return request<CaseDocument>(`/cases/${caseId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
  },

  // Documents
  async uploadDocument(caseId: string, file: File, role = 'applicant_document_bundle'): Promise<DocumentEntry> {
    if (isDemoMode()) return mockApi.uploadDocument(caseId, file, role)
    const form = new FormData()
    form.append('file', file)
    form.append('document_role', role)
    return request(`/cases/${caseId}/documents`, {
      method: 'POST',
      body: form,
    })
  },

  listDocuments(caseId: string): Promise<DocumentEntry[]> {
    if (isDemoMode()) return mockApi.listDocuments(caseId)
    return request<{ documents: DocumentEntry[] }>(`/cases/${caseId}/documents`).then(
      (r) => r.documents ?? [],
    )
  },

  getDocumentUrl(caseId: string, documentId: string): Promise<{ signed_url: string }> {
    if (isDemoMode()) return mockApi.getDocumentUrl(caseId, documentId)
    return request(`/cases/${caseId}/documents/${documentId}/url`)
  },

  getDocumentContentUrl(caseId: string, documentId: string): string {
    return `${BASE}/cases/${caseId}/documents/${documentId}/content`
  },

  getDocumentPreviewUrl(caseId: string, documentId: string, sheet?: string): string {
    const base = `${BASE}/cases/${caseId}/documents/${documentId}/preview`
    return sheet ? `${base}?sheet=${encodeURIComponent(sheet)}` : base
  },

  getDocumentSheets(caseId: string, documentId: string): Promise<{ sheets: string[] }> {
    if (isDemoMode()) return mockApi.getDocumentSheets(caseId, documentId)
    return request(`/cases/${caseId}/documents/${documentId}/sheets`)
  },

  // Extraction
  startExtraction(caseId: string, options?: { backend?: string; pattern?: string }) {
    if (isDemoMode()) return mockApi.startExtraction(caseId)
    return request<{ session_id: string; status: string; error?: string }>(`/cases/${caseId}/extract`, {
      method: 'POST',
      body: JSON.stringify({
        backend: options?.backend ?? 'gemini',
        pattern: options?.pattern ?? 'auto',
      }),
    })
  },

  getExtractionStatus(caseId: string) {
    if (isDemoMode()) return mockApi.getExtractionStatus(caseId)
    return request<{ status: string; session_id?: string }>(`/cases/${caseId}/extraction-status`)
  },

  /** SSE で抽出進捗をストリーム受信する（Gemini用） */
  startExtractionStream(
    caseId: string,
    options: { backend?: string; pattern?: string },
    callbacks: {
      onProgress: (data: { phase: string; message: string }) => void
      onComplete: (data: { workflow_state: string }) => void
      onError: (error: string) => void
    },
  ): { abort: () => void } {
    const controller = new AbortController()
    const startedAt = performance.now()

    ;(async () => {
      try {
        console.info('ui.extract.fetch_started', { caseId })
        const res = await fetch(`${BASE}/cases/${caseId}/extract-stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            backend: options.backend ?? 'gemini',
            pattern: options.pattern ?? 'auto',
          }),
          signal: controller.signal,
        })

        if (!res.ok) {
          const text = await res.text().catch(() => res.statusText)
          console.info('ui.extract.fetch_failed', {
            caseId,
            status: res.status,
            elapsed_ms: Math.round(performance.now() - startedAt),
          })
          callbacks.onError(`API error ${res.status}: ${text}`)
          return
        }
        console.info('ui.extract.response_opened', {
          caseId,
          elapsed_ms: Math.round(performance.now() - startedAt),
        })

        const reader = res.body?.getReader()
        if (!reader) {
          callbacks.onError('ReadableStream not supported')
          return
        }

        const decoder = new TextDecoder()
        let buffer = ''
        let finished = false

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const json = line.slice(6).trim()
            if (!json) continue

            try {
              const parsed = JSON.parse(json)
              const logBase = {
                caseId,
                run_id: parsed.run_id,
                elapsed_ms: Math.round(performance.now() - startedAt),
                server_elapsed_ms: parsed.elapsed_ms,
              }
              if (parsed.event === 'progress') {
                console.info('ui.extract.progress', { ...logBase, phase: parsed.phase })
                callbacks.onProgress({ phase: parsed.phase, message: parsed.message })
              } else if (parsed.event === 'complete') {
                finished = true
                console.info('ui.extract.complete', {
                  ...logBase,
                  workflow_state: parsed.workflow_state,
                })
                callbacks.onComplete({ workflow_state: parsed.workflow_state })
              } else if (parsed.event === 'error') {
                finished = true
                console.info('ui.extract.error', {
                  ...logBase,
                  error_type: typeof parsed.error,
                })
                callbacks.onError(parsed.error)
              }
            } catch {
              // ignore malformed JSON
            }
          }
        }

        if (!finished) {
          console.info('ui.extract.stream_closed_without_finish', {
            caseId,
            elapsed_ms: Math.round(performance.now() - startedAt),
          })
          callbacks.onError('抽出ストリームが完了前に切断されました')
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          console.info('ui.extract.connection_error', {
            caseId,
            elapsed_ms: Math.round(performance.now() - startedAt),
            error_type: (err as Error).name,
          })
          callbacks.onError((err as Error).message ?? '接続エラー')
        }
      }
    })()

    return { abort: () => controller.abort() }
  },
}
