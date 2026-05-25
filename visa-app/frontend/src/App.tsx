import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import CaseListPage from './pages/CaseListPage'
import UploadPage from './pages/UploadPage'
import ReviewPage from './pages/ReviewPage'

export default function App() {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3">
        <Link to={`/${location.search}`} className="text-lg font-semibold text-gray-800 hover:text-blue-600 transition-colors">
          ビザ申請レビュー
        </Link>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CaseListPage />} />
          <Route path="/cases/:caseId/upload" element={<UploadPage />} />
          <Route path="/cases/:caseId/review" element={<ReviewPage />} />
          <Route path="*" element={<Navigate to={`/${location.search}`} replace />} />
        </Routes>
      </main>
    </div>
  )
}
