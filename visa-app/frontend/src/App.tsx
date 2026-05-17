import { Routes, Route, Navigate } from 'react-router-dom'
import CaseListPage from './pages/CaseListPage'
import UploadPage from './pages/UploadPage'
import ReviewPage from './pages/ReviewPage'

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3">
        <h1 className="text-lg font-semibold text-gray-800">
          ビザ申請レビュー
        </h1>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CaseListPage />} />
          <Route path="/cases/:caseId/upload" element={<UploadPage />} />
          <Route path="/cases/:caseId/review" element={<ReviewPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
