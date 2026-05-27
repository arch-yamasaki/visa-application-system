const statusBox = document.querySelector("#status");
const RASENS_URL_PATTERNS = ["https://www.rasens-immi.moj.go.jp/*"];

function setStatus(message) {
  statusBox.textContent = message;
}

function setFillButtonsEnabled(enabled) {
  document.querySelector("#fill").disabled = !enabled;
  document.querySelector("#fillProgressive").disabled = !enabled;
}

async function clearRows(message) {
  await chrome.storage.local.remove(["visaRows", "visaDataSource", "visaFillable"]);
  setFillButtonsEnabled(false);
  if (message) {
    setStatus(message);
  }
}

async function saveRows(rows, source, canFill = true) {
  const inputRows = rows.filter((row) => (row.fill_value || "").trim());
  await chrome.storage.local.set({
    visaRows: inputRows,
    visaDataSource: source,
    visaFillable: inputRows.length > 0 && Boolean(canFill),
  });
  setFillButtonsEnabled(inputRows.length > 0 && Boolean(canFill));
  setStatus(`${source}\n${inputRows.length}件の入力値を保存しました`);
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function isRasensTab(tab) {
  try {
    const url = new URL(tab?.url || "");
    return url.protocol === "https:" && url.hostname === "www.rasens-immi.moj.go.jp";
  } catch {
    return false;
  }
}

async function getRasensTab() {
  const activeTab = await getActiveTab();
  if (isRasensTab(activeTab)) return activeTab;

  const rasensTabs = await chrome.tabs.query({ url: RASENS_URL_PATTERNS });
  if (rasensTabs.length === 1) return rasensTabs[0];
  if (rasensTabs.length > 1) {
    throw new Error("RASENSタブが複数あります。入力したいRASENSタブをアクティブにしてから実行してください");
  }
  throw new Error("在留申請オンラインシステムのページを開いてから実行してください");
}

async function ensureContentScript(tab) {
  if (!tab?.id) throw new Error("アクティブなタブを取得できませんでした");
  if (!isRasensTab(tab)) {
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
  const { visaRows, visaFillable } = await chrome.storage.local.get(["visaRows", "visaFillable"]);
  if (!visaRows?.length) {
    setStatus("先にデータを読み込んでください");
    return;
  }
  if (type !== "VISA_AUTOFILL_PREVIEW" && !visaFillable) {
    setStatus("このケースはまだ入力可能状態ではありません。入力対象の確認だけ実行できます。");
    return;
  }

  let tab;
  try {
    tab = await getRasensTab();
    try {
      setStatus("ページへ接続しています...");
      const message = await sendMessageOrThrow(tab, type, visaRows);
      setStatus(message);
    } catch (error) {
      await ensureContentScript(tab);
      const message = await sendMessageOrThrow(tab, type, visaRows);
      setStatus(message);
    }
  } catch (error) {
    setStatus(`ページに接続できませんでした\n${error.message}`);
  }
}

document.querySelector("#loadBundled").addEventListener("click", async () => {
  const response = await fetch(chrome.runtime.getURL("application_data.json"));
  await saveRows(await response.json(), "同梱JSON");
});

document.querySelector("#fill").addEventListener("click", () => sendToTab("VISA_AUTOFILL_FILL"));
document.querySelector("#fillProgressive").addEventListener("click", () => sendToTab("VISA_AUTOFILL_FILL_PROGRESSIVE"));
document.querySelector("#preview").addEventListener("click", () => sendToTab("VISA_AUTOFILL_PREVIEW"));

chrome.storage.local.get(["visaRows", "visaDataSource", "visaFillable"]).then(({ visaRows, visaDataSource, visaFillable }) => {
  if (visaRows?.length) {
    setFillButtonsEnabled(Boolean(visaFillable));
    setStatus(`${visaDataSource || "保存済みデータ"}\n${visaRows.length}件の入力値が保存されています`);
  } else {
    setFillButtonsEnabled(false);
  }
});

// --- visa-app API integration ---

const workflowStateLabel = {
  draft: "未抽出",
  extracting: "抽出中",
  extracted: "抽出済み",
  failed: "抽出失敗"
};

function toWorkflowDisplayState(workflowState) {
  if (workflowState === "extracting") return "extracting";
  if (workflowState === "needs_review" || workflowState === "ready_to_fill" || workflowState === "extracted") {
    return "extracted";
  }
  if (workflowState === "extraction_failed" || workflowState === "launch_failed" || workflowState === "failed") {
    return "failed";
  }
  return "draft";
}

document.querySelector("#setApiUrl").addEventListener("click", (e) => {
  e.preventDefault();
  const url = prompt("visa-app APIのURLを入力してください:", window.apiClient.defaultApiUrl);
  if (url?.trim()) {
    chrome.storage.local.set({ visaAppApiUrl: url.trim() });
    setStatus("API URL を保存しました");
  }
});

document.querySelector("#loadFromApi").addEventListener("click", async () => {
  const caseId = document.querySelector("#caseId").value.trim();
  if (!caseId) {
    setStatus("case_id を入力してください");
    return;
  }

  // Reset banners
  document.querySelector("#workflowWarning").hidden = true;
  document.querySelector("#workflowReady").hidden = true;

  try {
    setStatus("visa-app から取得中...");
    const applicationData = await window.apiClient.getApplicationData(caseId);

    const workflowState = applicationData.workflow_state;
    const displayState = toWorkflowDisplayState(workflowState);
    document.querySelector("#wfState").textContent = workflowStateLabel[displayState];
    if (applicationData.fillable) {
      document.querySelector("#workflowReady").hidden = false;
    } else {
      document.querySelector("#workflowWarning").hidden = false;
    }

    const rows = applicationData.rows || [];
    if (!rows.length) {
      await clearRows("入力対象の値がありません。visa-app のレビュー内容を確認してください。");
      return;
    }

    const warningText = (applicationData.warnings || []).join("\n");
    await saveRows(rows, `visa-app: ${caseId}`, applicationData.fillable);
    if (warningText) {
      setStatus(`visa-app: ${caseId}\n${rows.length}件の入力値を保存しました\n${warningText}`);
    }
  } catch (error) {
    await clearRows(`読込エラー\n${error.message}`);
  }
});
