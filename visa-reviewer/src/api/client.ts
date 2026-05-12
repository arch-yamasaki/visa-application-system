import type { CaseDocument, CaseSummary, DocumentEntry } from '../types/caseData'

const BASE = '/api'

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
    return request<{ case_id: string; workflow_state: string; created_at: string }>(
      '/cases',
      { method: 'POST', body: JSON.stringify(params) },
    )
  },

  listCases(): Promise<CaseSummary[]> {
    return request('/cases')
  },

  getCase(caseId: string): Promise<CaseDocument> {
    return request(`/cases/${caseId}`)
  },

  updateCase(
    caseId: string,
    updates: { case_data?: unknown; field_metadata?: unknown; workflow_state?: string },
  ) {
    return request<CaseDocument>(`/cases/${caseId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
  },

  // Documents
  async uploadDocument(caseId: string, file: File, role = 'applicant_document_bundle'): Promise<DocumentEntry> {
    const form = new FormData()
    form.append('file', file)
    form.append('document_role', role)
    return request(`/cases/${caseId}/documents`, {
      method: 'POST',
      body: form,
    })
  },

  listDocuments(caseId: string): Promise<DocumentEntry[]> {
    return request<{ documents: DocumentEntry[] }>(`/cases/${caseId}/documents`).then(
      (r) => r.documents ?? [],
    )
  },

  getDocumentUrl(caseId: string, documentId: string): Promise<{ signed_url: string }> {
    return request(`/cases/${caseId}/documents/${documentId}/url`)
  },

  // Extraction
  startExtraction(caseId: string) {
    return request<{ session_id: string; status: string }>(`/cases/${caseId}/extract`, {
      method: 'POST',
    })
  },

  getExtractionStatus(caseId: string) {
    return request<{ status: string; session_id?: string }>(`/cases/${caseId}/extraction-status`)
  },
}
