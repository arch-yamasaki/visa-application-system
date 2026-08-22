import type { CaseDocument, CaseSummary, DocumentEntry } from '../types/caseData'
import { authHeaders } from '../auth/firebase'
import { mockApi } from './mockData'

const BASE = '/api'

export interface CurrentUser {
  uid: string
  email: string
  org_id: string
  role: 'admin' | 'member' | string
}

export interface OrgSettings {
  org_id: string
  intermediary: {
    name: string
    postal_code: string
    address: string
    organization: string
    phone: string
  }
  receiving_method: {
    method: string
    notification_email: string
  }
  updated_at: string | null
  updated_by_uid: string | null
  can_update: boolean
}

export function isDemoMode(): boolean {
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
      ...(await authHeaders()),
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
  getMe(): Promise<CurrentUser> {
    if (isDemoMode()) {
      return Promise.resolve({ uid: 'demo', email: 'demo@example.com', org_id: 'demo', role: 'admin' })
    }
    return request('/me')
  },

  getOrgSettings(): Promise<OrgSettings> {
    if (isDemoMode()) {
      return Promise.resolve({
        org_id: 'demo',
        intermediary: { name: '', postal_code: '', address: '', organization: '', phone: '' },
        receiving_method: { method: 'メール Email', notification_email: '' },
        updated_at: null,
        updated_by_uid: null,
        can_update: true,
      })
    }
    return request('/org-settings')
  },

  updateOrgSettings(settings: Pick<OrgSettings, 'intermediary' | 'receiving_method'>): Promise<OrgSettings> {
    if (isDemoMode()) {
      return Promise.resolve({
        org_id: 'demo',
        ...settings,
        receiving_method: {
          method: 'メール Email',
          notification_email: settings.receiving_method.notification_email,
        },
        updated_at: new Date().toISOString(),
        updated_by_uid: 'demo',
        can_update: true,
      })
    }
    return request('/org-settings', { method: 'PATCH', body: JSON.stringify(settings) })
  },

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
    updates: { case_data?: unknown; field_metadata?: unknown; workflow_state?: string },
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

  /** 認証付きで書類を取得し、viewer に渡せる objectURL を返す。呼び出し側で revoke する。 */
  async getDocumentBlobUrl(caseId: string, documentId: string): Promise<string> {
    if (isDemoMode()) return (await mockApi.getDocumentUrl(caseId, documentId)).signed_url
    const res = await fetch(`${BASE}/cases/${caseId}/documents/${documentId}/content`, {
      headers: await authHeaders(),
    })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new Error(`API error ${res.status}: ${text}`)
    }
    return URL.createObjectURL(await res.blob())
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
          headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
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
          const latest = await request<CaseDocument>(`/cases/${caseId}`).catch(() => null)
          if (latest?.workflow_state === 'extracted') {
            callbacks.onComplete({ workflow_state: latest.workflow_state })
            return
          }
          if (latest?.workflow_state === 'failed') {
            callbacks.onError(latest.extraction?.error ?? '抽出に失敗しました。サーバー側の状態を確認してください。')
            return
          }
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
