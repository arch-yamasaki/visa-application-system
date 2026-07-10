import { useEffect } from 'react'
import { useAuthStore } from '../store/authStore'
import { LoginForm } from './LoginPage'

// Chrome拡張の chrome.identity.launchWebAuthFlow から開かれる認証ページ。
// ログイン完了後(Google・メール/パスワードどちらでも)、refresh token を
// 拡張のリダイレクトURL(chromiumapp.org)へフラグメントで返す。
// 拡張IDは a-p の32文字。それ以外のリダイレクト先へはトークンを渡さない。
const REDIRECT_URI_PATTERN = /^https:\/\/[a-p]{32}\.chromiumapp\.org\//

export default function ExtensionAuthPage() {
  const user = useAuthStore((s) => s.user)
  const initialized = useAuthStore((s) => s.initialized)
  const redirectUri = new URLSearchParams(window.location.search).get('redirect_uri') ?? ''
  const redirectValid = REDIRECT_URI_PATTERN.test(redirectUri)

  useEffect(() => {
    if (!user || !redirectValid) return
    const params = new URLSearchParams({
      refresh_token: user.refreshToken,
      email: user.email ?? '',
    })
    window.location.replace(`${redirectUri}#${params.toString()}`)
  }, [user, redirectUri, redirectValid])

  if (!redirectValid) {
    return (
      <div className="pt-24 text-center text-sm text-red-600">
        不正なリダイレクト先が指定されました。Chrome拡張からやり直してください。
      </div>
    )
  }
  if (!initialized) {
    return <div className="pt-24 text-center text-sm text-gray-400">読み込み中...</div>
  }
  if (user) {
    return <div className="pt-24 text-center text-sm text-gray-400">拡張機能へ戻ります...</div>
  }
  return <LoginForm />
}
