import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { FirebaseError } from 'firebase/app'
import { GoogleAuthProvider, signInWithEmailAndPassword, signInWithPopup } from 'firebase/auth'
import { firebaseAuth } from '../auth/firebase'
import { useAuthStore } from '../store/authStore'

const ERROR_MESSAGES: Record<string, string> = {
  'auth/invalid-credential': 'メールアドレスまたはパスワードが正しくありません',
  'auth/invalid-email': 'メールアドレスの形式が正しくありません',
  'auth/too-many-requests': '試行回数が多すぎます。しばらく待ってから再試行してください',
  'auth/popup-closed-by-user': 'ログインがキャンセルされました',
}

function loginErrorMessage(err: unknown): string {
  if (err instanceof FirebaseError) {
    return ERROR_MESSAGES[err.code] ?? `ログインに失敗しました (${err.code})`
  }
  return 'ログインに失敗しました'
}

export default function LoginPage() {
  const user = useAuthStore((s) => s.user)

  if (user) return <Navigate to="/" replace />
  return <LoginForm />
}

/** ログインフォーム本体。/login と /extension-auth の両方から使う。 */
export function LoginForm() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const signIn = async (action: () => Promise<unknown>) => {
    setError(null)
    setSubmitting(true)
    try {
      await action()
    } catch (err) {
      setError(loginErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex items-center justify-center pt-24">
      <div className="w-full max-w-sm bg-white border border-gray-200 rounded-lg shadow-sm p-8">
        <h1 className="text-lg font-semibold text-gray-800 mb-6">ログイン</h1>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void signIn(() => signInWithEmailAndPassword(firebaseAuth, email, password))
          }}
        >
          <div>
            <label className="block text-xs text-gray-500 mb-1" htmlFor="email">
              メールアドレス
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1" htmlFor="password">
              パスワード
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            ログイン
          </button>
        </form>
        <div className="flex items-center gap-3 my-4 text-xs text-gray-400">
          <div className="flex-1 border-t border-gray-200" />
          または
          <div className="flex-1 border-t border-gray-200" />
        </div>
        <button
          onClick={() => void signIn(() => signInWithPopup(firebaseAuth, new GoogleAuthProvider()))}
          disabled={submitting}
          className="w-full py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
        >
          Googleでログイン
        </button>
        <p className="mt-6 text-xs text-gray-400">
          アカウントは管理者が発行します。ログインできない場合は管理者に連絡してください。
        </p>
      </div>
    </div>
  )
}
