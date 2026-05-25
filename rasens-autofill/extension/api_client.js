/**
 * visa-app API client for Chrome extension.
 * Fetches generated application-data rows from visa-app backend.
 */

/**
 * Retrieve visa-app API URL from chrome.storage.local.
 * @returns {Promise<string>}
 */
async function getApiUrl() {
  const { visaAppApiUrl } = await chrome.storage.local.get(["visaAppApiUrl"]);
  if (!visaAppApiUrl) {
    throw new Error("API URLが未設定です。設定画面からAPI URLを入力してください。");
  }
  return visaAppApiUrl;
}

/**
 * Fetch a case's application-data rows from visa-app API.
 * @param {string} caseId
 * @returns {Promise<object>} application-data response
 */
async function getApplicationData(caseId) {
  const apiUrl = await getApiUrl();
  const url = `${apiUrl}/cases/${encodeURIComponent(caseId)}/application-data`;

  const response = await fetch(url);

  if (response.status === 404) {
    throw new Error(`ケース「${caseId}」が見つかりません。case_id を確認してください。`);
  }
  if (response.status === 401 || response.status === 403) {
    throw new Error("認証エラー: アクセス権限がありません。");
  }
  if (!response.ok) {
    throw new Error(`API エラー (${response.status}): ${response.statusText}`);
  }

  return await response.json();
}

/**
 * Fetch case list from visa-app API.
 * @returns {Promise<Array>} Array of case summary objects
 */
async function listCases() {
  const apiUrl = await getApiUrl();
  const url = `${apiUrl}/cases?workflow_state=ready_to_fill&limit=20`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`API エラー (${response.status}): ${response.statusText}`);
  }

  return await response.json();
}

// Export for use by popup.js
window.apiClient = { getApplicationData, listCases };
