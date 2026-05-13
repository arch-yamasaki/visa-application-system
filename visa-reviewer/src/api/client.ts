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

  getDocumentUrl(caseId: string, documentId: string): Promise<{ signed_url: string }> {
    if (isDemoMode()) return mockApi.getDocumentUrl(caseId, documentId)
    return request(`/cases/${caseId}/documents/${documentId}/url`)
  },

  // Extraction
  startExtraction(caseId: string, options?: { backend?: string; pattern?: string }) {
    if (isDemoMode()) return mockApi.startExtraction(caseId)
    return request<{ session_id: string; status: string }>(`/cases/${caseId}/extract`, {
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
}
