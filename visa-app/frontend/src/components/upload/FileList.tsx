import type { DocumentEntry } from '../../types/caseData'

const roleLabels: Record<string, string> = {
  applicant_document_bundle: '申請人書類',
  employment_terms: '雇用条件通知書',
  company_documents: '会社書類',
  intake_spreadsheet: '受付シート',
  other: 'その他',
}

interface Props {
  documents: DocumentEntry[]
}

export default function FileList({ documents }: Props) {
  if (documents.length === 0) return null

  return (
    <div className="mt-4">
      <h3 className="text-sm font-medium text-gray-700 mb-2">
        アップロード済み ({documents.length})
      </h3>
      <ul className="space-y-1">
        {documents.map((doc) => (
          <li
            key={doc.document_id}
            className="flex items-center gap-3 px-3 py-2 bg-white rounded-lg border border-gray-200 text-sm"
          >
            <span className="text-gray-400 text-xs font-mono">{doc.document_id}</span>
            <span className="font-medium text-gray-700 flex-1 truncate">
              {doc.file_name}
            </span>
            <span className="text-xs text-gray-400">
              {roleLabels[doc.document_role] || doc.document_role}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
