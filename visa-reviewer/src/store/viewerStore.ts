import { create } from 'zustand'
import type { DocumentEntry, SourceRef } from '../types/caseData'

interface ViewerState {
  documents: DocumentEntry[]
  currentDocumentId: string | null
  currentPage: number
  highlightText: string | null
  signedUrls: Record<string, string>
  activeFieldPath: string | null

  setDocuments: (docs: DocumentEntry[]) => void
  setSignedUrl: (docId: string, url: string) => void
  navigateToSource: (ref: SourceRef) => void
  setPage: (page: number) => void
  clearHighlight: () => void
  setActiveFieldPath: (path: string | null) => void
}

export const useViewerStore = create<ViewerState>((set) => ({
  documents: [],
  currentDocumentId: null,
  currentPage: 1,
  highlightText: null,
  signedUrls: {},
  activeFieldPath: null,

  setDocuments: (docs) =>
    set({ documents: docs, currentDocumentId: docs[0]?.document_id ?? null }),

  setSignedUrl: (docId, url) =>
    set((s) => ({ signedUrls: { ...s.signedUrls, [docId]: url } })),

  navigateToSource: (ref) =>
    set({
      currentDocumentId: ref.document_id,
      currentPage: ref.page || 1,
      highlightText: ref.text_quote || null,
    }),

  setPage: (page) => set({ currentPage: page, highlightText: null }),

  clearHighlight: () => set({ highlightText: null }),

  setActiveFieldPath: (path) => set({ activeFieldPath: path }),
}))
