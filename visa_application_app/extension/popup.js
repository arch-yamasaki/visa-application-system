const statusBox = document.querySelector("#status");

function setStatus(message) {
  statusBox.textContent = message;
}

async function saveRows(rows, source) {
  const fillable = rows.filter((row) => (row.fill_value || "").trim());
  await chrome.storage.local.set({ visaRows: fillable, visaDataSource: source });
  setStatus(`${source}\n${fillable.length}件の入力値を保存しました`);
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function ensureContentScript(tab) {
  if (!tab?.id) throw new Error("アクティブなタブを取得できませんでした");
  if (!tab.url?.startsWith("https://www.rasens-immi.moj.go.jp/")) {
    throw new Error("在留申請オンラインシステムのページで実行してください");
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content.js"]
  });
}

async function sendMessageOrThrow(tab, type, rows) {
  const response = await chrome.tabs.sendMessage(tab.id, { type, rows });
  if (!response?.message) {
    throw new Error("ページ側の入力スクリプトが古いか、応答が空です");
  }
  return response.message;
}

async function sendToTab(type) {
  const { visaRows } = await chrome.storage.local.get(["visaRows"]);
  if (!visaRows?.length) {
    setStatus("先にデータを読み込んでください");
    return;
  }

  const tab = await getActiveTab();
  try {
    setStatus("ページへ接続しています...");
    const message = await sendMessageOrThrow(tab, type, visaRows);
    setStatus(message);
  } catch (error) {
    try {
      await ensureContentScript(tab);
      const message = await sendMessageOrThrow(tab, type, visaRows);
      setStatus(message);
    } catch (retryError) {
      setStatus(`ページに接続できませんでした\n${retryError.message || error.message}`);
    }
  }
}

document.querySelector("#loadBundled").addEventListener("click", async () => {
  const response = await fetch(chrome.runtime.getURL("application_data.json"));
  await saveRows(await response.json(), "同梱JSON");
});

document.querySelector("#fill").addEventListener("click", () => sendToTab("VISA_AUTOFILL_FILL"));
document.querySelector("#fillProgressive").addEventListener("click", () => sendToTab("VISA_AUTOFILL_FILL_PROGRESSIVE"));
document.querySelector("#preview").addEventListener("click", () => sendToTab("VISA_AUTOFILL_PREVIEW"));

chrome.storage.local.get(["visaRows", "visaDataSource"]).then(({ visaRows, visaDataSource }) => {
  if (visaRows?.length) {
    setStatus(`${visaDataSource || "保存済みデータ"}\n${visaRows.length}件の入力値が保存されています`);
  }
});
