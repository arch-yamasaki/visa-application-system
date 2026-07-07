import { initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

// Firebase Web アプリ設定 (visa-codex-mvp / visa-app)。
// apiKey は秘密情報ではなく、アクセス制御は backend の require_user
// (users コレクション照合) が担う。
const firebaseConfig = {
  apiKey: 'AIzaSyAV_Ho87O5xFV0QkTVRR_uyST6RfjNWkws',
  authDomain: 'visa-codex-mvp.firebaseapp.com',
  projectId: 'visa-codex-mvp',
  appId: '1:913363513517:web:01eb4516f1960e842c5624',
}

export const firebaseAuth = getAuth(initializeApp(firebaseConfig))

/** ログイン済みなら Authorization ヘッダを返す。トークン更新は SDK が行う。 */
export async function authHeaders(): Promise<Record<string, string>> {
  const user = firebaseAuth.currentUser
  return user ? { Authorization: `Bearer ${await user.getIdToken()}` } : {}
}
