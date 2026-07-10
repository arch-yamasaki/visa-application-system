/**
 * visa-app API client for Chrome extension.
 * Fetches generated application-data rows from visa-app backend.
 *
 * 認証: Firebase Authentication (メール/パスワード) の REST API でログインし、
 * refresh token を chrome.storage.local に保存する。API 呼び出しには
 * ID token (約1時間で失効、期限前に自動refresh) を Bearer で付与する。
 */

const DEFAULT_API_URL = "https://visa-app-913363513517.asia-northeast1.run.app";
const FIREBASE_API_KEY = "AIzaSyAV_Ho87O5xFV0QkTVRR_uyST6RfjNWkws";

const SIGN_IN_ERROR_MESSAGES = {
  INVALID_LOGIN_CREDENTIALS: "メールアドレスまたはパスワードが正しくありません",
  INVALID_EMAIL: "メールアドレスの形式が正しくありません",
  TOO_MANY_ATTEMPTS_TRY_LATER: "試行回数が多すぎます。しばらく待ってから再試行してください",
};

/**
 * メール/パスワードでログインし、トークンを保存する。
 */
async function signIn(email, password) {
  const response = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${FIREBASE_API_KEY}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, returnSecureToken: true }),
    }
  );
  const data = await response.json();
  if (!response.ok) {
    const code = data.error?.message;
    throw new Error(SIGN_IN_ERROR_MESSAGES[code] || `ログインに失敗しました (${code || "不明なエラー"})`);
  }
  await chrome.storage.local.set({
    visaAuth: {
      email,
      refreshToken: data.refreshToken,
      idToken: data.idToken,
      expiresAt: Date.now() + Number(data.expiresIn) * 1000,
    },
  });
}

/**
 * ブラウザ(visa-appのWebログイン画面)経由でログインする。
 * Googleログイン・メール/パスワードの両方が使え、visa-appのWebに
 * ログイン済みのブラウザなら追加操作なしで完了する。
 */
async function signInWithBrowser() {
  const redirectUri = chrome.identity.getRedirectURL();
  const authUrl = `${DEFAULT_API_URL}/extension-auth?redirect_uri=${encodeURIComponent(redirectUri)}`;
  const responseUrl = await chrome.identity.launchWebAuthFlow({ url: authUrl, interactive: true });
  const params = new URLSearchParams(new URL(responseUrl).hash.slice(1));
  const refreshToken = params.get("refresh_token");
  if (!refreshToken) {
    throw new Error("ログイン情報を取得できませんでした。もう一度お試しください");
  }
  await chrome.storage.local.set({
    visaAuth: {
      email: params.get("email") || "",
      refreshToken,
      idToken: "",
      expiresAt: 0, // 初回のAPI呼び出し時に getIdToken() がリフレッシュする
    },
  });
}

async function signOut() {
  await chrome.storage.local.remove("visaAuth");
}

/** ログイン中なら { email, ... } を、未ログインなら null を返す。 */
async function getAuthState() {
  const { visaAuth } = await chrome.storage.local.get("visaAuth");
  return visaAuth || null;
}

async function getIdToken() {
  const auth = await getAuthState();
  if (!auth) {
    throw new Error("ログインしてください");
  }
  if (Date.now() < auth.expiresAt - 60_000) {
    return auth.idToken;
  }

  const response = await fetch(
    `https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: `grant_type=refresh_token&refresh_token=${encodeURIComponent(auth.refreshToken)}`,
    }
  );
  const data = await response.json();
  if (!response.ok) {
    await signOut();
    throw new Error("ログインの有効期限が切れました。再ログインしてください");
  }
  const refreshed = {
    ...auth,
    refreshToken: data.refresh_token,
    idToken: data.id_token,
    expiresAt: Date.now() + Number(data.expires_in) * 1000,
  };
  await chrome.storage.local.set({ visaAuth: refreshed });
  return refreshed.idToken;
}

async function authorizedFetch(url) {
  const token = await getIdToken();
  return fetch(url, { headers: { Authorization: `Bearer ${token}` } });
}

/**
 * Fetch a case's application-data rows from visa-app API.
 * @param {string} caseId
 * @returns {Promise<object>} application-data response
 */
async function getApplicationData(caseId) {
  const url = `${DEFAULT_API_URL}/cases/${encodeURIComponent(caseId)}/application-data`;

  const response = await authorizedFetch(url);

  if (response.status === 404) {
    throw new Error(`ケース「${caseId}」が見つかりません。案件一覧を更新してください。`);
  }
  if (response.status === 401 || response.status === 403) {
    throw new Error("認証エラー: アクセス権限がありません。管理者にユーザー登録を依頼してください。");
  }
  if (!response.ok) {
    throw new Error(`API エラー (${response.status}): ${response.statusText}`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("APIからJSONが返りませんでした。visa-appを最新のバックエンドでデプロイしてください。");
  }

  return await response.json();
}

/**
 * Fetch case list from visa-app API.
 * @returns {Promise<Array>} Array of case summary objects
 */
async function listCases() {
  const url = `${DEFAULT_API_URL}/cases?limit=100`;

  const response = await authorizedFetch(url);

  if (response.status === 401 || response.status === 403) {
    throw new Error("認証エラー: アクセス権限がありません。管理者にユーザー登録を依頼してください。");
  }
  if (!response.ok) {
    throw new Error(`API エラー (${response.status}): ${response.statusText}`);
  }

  return await response.json();
}

// Export for use by popup.js
window.apiClient = { getApplicationData, listCases, signIn, signInWithBrowser, signOut, getAuthState };
