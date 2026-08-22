import { Routes, Route, Navigate, Link, Outlet, useLocation } from 'react-router-dom'
import CaseListPage from './pages/CaseListPage'
import UploadPage from './pages/UploadPage'
import ReviewPage from './pages/ReviewPage'
import LoginPage from './pages/LoginPage'
import ExtensionAuthPage from './pages/ExtensionAuthPage'
import OrgSettingsPage from './pages/OrgSettingsPage'
import { isDemoMode } from './api/client'
import { useAuthStore } from './store/authStore'

function RequireAuth() {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)

  if (isDemoMode()) return <Outlet />
  if (!initialized) {
    return (
      <div className="flex items-center justify-center pt-24 text-gray-400 text-sm">
        読み込み中...
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}

function HeaderUser() {
  const user = useAuthStore((s) => s.user)
  const signOut = useAuthStore((s) => s.signOut)
  const location = useLocation()

  if (!user) return null
  return (
    <div className="flex items-center gap-3 text-xs text-gray-500">
      <span>{user.email}</span>
      <Link to={`/settings${location.search}`} className="hover:text-blue-600">
        組織設定
      </Link>
      <button
        onClick={() => void signOut()}
        className="px-2 py-1 border border-gray-300 rounded hover:bg-gray-50"
      >
        ログアウト
      </button>
    </div>
  )
}

export default function App() {
  const location = useLocation()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <Link to={`/${location.search}`} className="text-lg font-semibold text-gray-800 hover:text-blue-600 transition-colors">
          ビザ申請レビュー
        </Link>
        <HeaderUser />
      </header>
      <main>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/extension-auth" element={<ExtensionAuthPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<CaseListPage />} />
            <Route path="/settings" element={<OrgSettingsPage />} />
            <Route path="/cases/:caseId/upload" element={<UploadPage />} />
            <Route path="/cases/:caseId/review" element={<ReviewPage />} />
          </Route>
          <Route path="*" element={<Navigate to={`/${location.search}`} replace />} />
        </Routes>
      </main>
    </div>
  )
}
