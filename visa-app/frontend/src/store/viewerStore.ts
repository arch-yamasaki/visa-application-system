import { create } from 'zustand'
import type { DocumentEntry, SourceRef } from '../types/caseData'

interface ViewerState {
  documents: DocumentEntry[]
  currentDocumentId: string | null
  currentPage: number
  highlightText: string | null
  highlightSourceRef: SourceRef | null
  activeFieldPath: string | null
  activeCandidateIndex: number

  setDocuments: (docs: DocumentEntry[]) => void
  navigateToSource: (ref: SourceRef) => void
  selectDocument: (docId: string) => void
  setPage: (page: number) => void
  clearHighlight: () => void
  setActiveFieldPath: (path: string | null) => void
  goToCandidate: (index: number) => void
}

export const useViewerStore = create<ViewerState>((set) => ({
  documents: [],
  currentDocumentId: null,
  currentPage: 1,
  highlightText: null,
  highlightSourceRef: null,
  activeFieldPath: null,
  activeCandidateIndex: 0,

  setDocuments: (docs) =>
    set({ documents: docs, currentDocumentId: docs[0]?.document_id ?? null }),

  navigateToSource: (ref) =>
    set(() => {
      return {
        currentDocumentId: ref.document_id,
        currentPage: ref.anchor?.page || ref.anchor?.candidates?.[0]?.page || ref.page || 1,
        highlightText: ref.text_quote || null,
        highlightSourceRef: ref,
        activeCandidateIndex: 0,
      }
    }),

  // 候補間の移動ではハイライト対象を保ったままページだけ追従させる
  goToCandidate: (index) =>
    set((s) => {
      const candidates = s.highlightSourceRef?.anchor?.candidates ?? []
      const candidate = candidates[index]
      if (!candidate) return {}
      return {
        activeCandidateIndex: index,
        currentPage: candidate.page ?? s.currentPage,
      }
    }),

  selectDocument: (docId) =>
    set({
      currentDocumentId: docId,
      currentPage: 1,
      highlightText: null,
      highlightSourceRef: null,
      activeFieldPath: null,
    }),

  setPage: (page) => set({ currentPage: page, highlightText: null, highlightSourceRef: null }),

  clearHighlight: () => set({ highlightText: null, highlightSourceRef: null }),

  setActiveFieldPath: (path) => set({ activeFieldPath: path }),
}))
