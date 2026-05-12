/**
 * Lightweight Firestore REST API client for Chrome extension.
 * No Firebase SDK dependency — uses fetch directly.
 */

const FIRESTORE_BASE = "https://firestore.googleapis.com/v1/projects/visa-codex-mvp/databases/(default)/documents";

/**
 * Convert Firestore REST response fields to plain JSON.
 * Handles stringValue, integerValue, booleanValue, doubleValue,
 * mapValue, arrayValue, nullValue, timestampValue.
 */
function firestoreValueToPlain(value) {
  if (value == null) return null;
  if ("stringValue" in value) return value.stringValue;
  if ("integerValue" in value) return Number(value.integerValue);
  if ("booleanValue" in value) return value.booleanValue;
  if ("doubleValue" in value) return value.doubleValue;
  if ("nullValue" in value) return null;
  if ("timestampValue" in value) return value.timestampValue;
  if ("mapValue" in value) return firestoreFieldsToPlain(value.mapValue.fields || {});
  if ("arrayValue" in value) {
    return (value.arrayValue.values || []).map(firestoreValueToPlain);
  }
  return value;
}

function firestoreFieldsToPlain(fields) {
  const result = {};
  for (const [key, val] of Object.entries(fields)) {
    result[key] = firestoreValueToPlain(val);
  }
  return result;
}

/**
 * Retrieve API key from chrome.storage.local.
 * @returns {Promise<string>}
 */
async function getApiKey() {
  const { firestoreApiKey } = await chrome.storage.local.get(["firestoreApiKey"]);
  if (!firestoreApiKey) {
    throw new Error("API Keyが未設定です。設定画面からAPI Keyを入力してください。");
  }
  return firestoreApiKey;
}

/**
 * Fetch a case document from Firestore.
 * @param {string} caseId
 * @returns {Promise<object>} Plain JSON object of the case document
 */
async function getCase(caseId) {
  const apiKey = await getApiKey();
  const url = `${FIRESTORE_BASE}/cases/${encodeURIComponent(caseId)}?key=${encodeURIComponent(apiKey)}`;

  const response = await fetch(url);

  if (response.status === 404) {
    throw new Error(`ケース「${caseId}」が見つかりません。case_id を確認してください。`);
  }
  if (response.status === 401 || response.status === 403) {
    throw new Error("認証エラー: API Keyが無効か、アクセス権限がありません。");
  }
  if (!response.ok) {
    throw new Error(`Firestore API エラー (${response.status}): ${response.statusText}`);
  }

  const doc = await response.json();
  return firestoreFieldsToPlain(doc.fields || {});
}

// Export for use by popup.js
window.firestoreClient = { getCase, getApiKey };
