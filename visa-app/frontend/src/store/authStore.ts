import { onAuthStateChanged, signOut, type User } from 'firebase/auth'
import { create } from 'zustand'
import { firebaseAuth } from '../auth/firebase'

interface AuthState {
  user: User | null
  /** onAuthStateChanged の初回通知を受け取るまで false */
  initialized: boolean
  signOut: () => Promise<void>
}

export const useAuthStore = create<AuthState>(() => ({
  user: null,
  initialized: false,
  signOut: () => signOut(firebaseAuth),
}))

onAuthStateChanged(firebaseAuth, (user) => {
  useAuthStore.setState({ user, initialized: true })
})
