/**
 * visa-app API client for Chrome extension.
 * Fetches generated application-data rows from visa-app backend.
 */

const DEFAULT_API_URL = "https://visa-app-913363513517.asia-northeast1.run.app";

/**
 * Fetch a case's application-data rows from visa-app API.
 * @param {string} caseId
 * @returns {Promise<object>} application-data response
 */
async function getApplicationData(caseId) {
  const url = `${DEFAULT_API_URL}/cases/${encodeURIComponent(caseId)}/application-data`;

  const response = await fetch(url);

  if (response.status === 404) {
    throw new Error(`ケース「${caseId}」が見つかりません。案件一覧を更新してください。`);
  }
  if (response.status === 401 || response.status === 403) {
    throw new Error("認証エラー: アクセス権限がありません。");
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

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`API エラー (${response.status}): ${response.statusText}`);
  }

  return await response.json();
}

// Export for use by popup.js
window.apiClient = { getApplicationData, listCases };
