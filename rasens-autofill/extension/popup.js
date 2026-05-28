const elements = {
  statusBox: document.querySelector("#status"),
  caseSelect: document.querySelector("#caseSelect"),
  caseListStatus: document.querySelector("#caseListStatus"),
  caseIdInput: document.querySelector("#caseId"),
  refreshCases: document.querySelector("#refreshCases"),
  loadBundled: document.querySelector("#loadBundled"),
  loadFromApi: document.querySelector("#loadFromApi"),
  fill: document.querySelector("#fill"),
  fillProgressive: document.querySelector("#fillProgressive"),
  preview: document.querySelector("#preview"),
  setApiUrl: document.querySelector("#setApiUrl"),
  workflowWarning: document.querySelector("#workflowWarning"),
  workflowReady: document.querySelector("#workflowReady"),
  workflowState: document.querySelector("#wfState"),
};
const RASENS_URL_PATTERNS = ["https://www.rasens-immi.moj.go.jp/*"];
let availableCases = [];

function setStatus(message) {
  elements.statusBox.textContent = message;
}

function setCaseListStatus(message) {
  elements.caseListStatus.textContent = message;
}

function setFillButtonsEnabled(enabled) {
  elements.fill.disabled = !enabled;
  elements.fillProgressive.disabled = !enabled;
}

function resetWorkflowBanners() {
  elements.workflowWarning.hidden = true;
  elements.workflowReady.hidden = true;
  elements.workflowState.textContent = "";
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

function formatWorkflowState(workflowState) {
  if (!workflowState) {
    return "未抽出";
  }
  const displayState = toWorkflowDisplayState(workflowState);
  return workflowStateLabel[displayState] || workflowState;
}

function formatCaseOptionLabel(caseSummary) {
  const displayName = caseSummary.display_name || caseSummary.case_id;
  const applicantName = caseSummary.applicant_name || "-";
  const employerName = caseSummary.employer_name || "-";
  const workflowState = formatWorkflowState(caseSummary.workflow_state);
  return `${displayName} | 申請人: ${applicantName} | 所属先: ${employerName} | 状態: ${workflowState}`;
}

function getCaseSummary(caseId) {
  return availableCases.find((caseSummary) => caseSummary.case_id === caseId) || null;
}

function renderCaseOptions(cases, selectedCaseId = "", placeholderText = "案件を選択してください") {
  elements.caseSelect.replaceChildren();

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = placeholderText;
  elements.caseSelect.appendChild(placeholder);

  for (const caseSummary of cases) {
    const option = document.createElement("option");
    option.value = caseSummary.case_id;
    option.textContent = formatCaseOptionLabel(caseSummary);
    elements.caseSelect.appendChild(option);
  }

  elements.caseSelect.value = cases.some((caseSummary) => caseSummary.case_id === selectedCaseId)
    ? selectedCaseId
    : "";
  if (elements.caseSelect.value) {
    elements.caseIdInput.value = elements.caseSelect.value;
  }
  elements.caseSelect.disabled = cases.length === 0;
}

async function loadCases() {
  const { visaSelectedCaseId = "" } = await chrome.storage.local.get(["visaSelectedCaseId"]);

  elements.refreshCases.disabled = true;
  elements.caseSelect.disabled = true;
  setCaseListStatus("案件一覧を取得中...");

  try {
    const cases = await window.apiClient.listCases();
    availableCases = Array.isArray(cases)
      ? cases.filter((caseSummary) => caseSummary?.case_id)
      : [];

    renderCaseOptions(
      availableCases,
      visaSelectedCaseId,
      availableCases.length ? "案件を選択してください" : "案件がありません"
    );

    if (availableCases.length) {
      setCaseListStatus(`${availableCases.length}件の案件を取得しました`);
    } else {
      setCaseListStatus("案件がありません。必要なら case_id を手入力してください");
    }
  } catch (error) {
    availableCases = [];
    renderCaseOptions([], "", "案件一覧を取得できませんでした");
    setCaseListStatus(`案件一覧の取得に失敗しました。case_id を手入力してください: ${error.message}`);
  } finally {
    elements.refreshCases.disabled = false;
    elements.caseSelect.disabled = availableCases.length === 0;
  }
}

function getRequestedCase() {
  const selectedCaseId = elements.caseSelect.value.trim();
  if (selectedCaseId) {
    return { caseId: selectedCaseId, caseSummary: getCaseSummary(selectedCaseId) };
  }

  const manualCaseId = elements.caseIdInput.value.trim();
  if (manualCaseId) {
    return { caseId: manualCaseId, caseSummary: null };
  }

  return null;
}

function getCaseSourceLabel(caseId, caseSummary) {
  const displayName = caseSummary?.display_name?.trim();
  if (displayName) {
    return `visa-app: ${displayName} (${caseId})`;
  }
  return `visa-app: ${caseId}`;
}

elements.loadBundled.addEventListener("click", async () => {
  const response = await fetch(chrome.runtime.getURL("application_data.json"));
  await saveRows(await response.json(), "同梱JSON");
});

elements.fill.addEventListener("click", () => sendToTab("VISA_AUTOFILL_FILL"));
elements.fillProgressive.addEventListener("click", () => sendToTab("VISA_AUTOFILL_FILL_PROGRESSIVE"));
elements.preview.addEventListener("click", () => sendToTab("VISA_AUTOFILL_PREVIEW"));

elements.caseSelect.addEventListener("change", async () => {
  const selectedCaseId = elements.caseSelect.value.trim();
  if (selectedCaseId) {
    elements.caseIdInput.value = selectedCaseId;
  }
  await chrome.storage.local.set({ visaSelectedCaseId: selectedCaseId });
});

elements.caseIdInput.addEventListener("input", async () => {
  if (!elements.caseIdInput.value.trim() || !elements.caseSelect.value) {
    return;
  }
  elements.caseSelect.value = "";
  await chrome.storage.local.set({ visaSelectedCaseId: "" });
});

elements.refreshCases.addEventListener("click", () => {
  loadCases();
});

elements.setApiUrl.addEventListener("click", (event) => {
  event.preventDefault();
  const url = prompt("visa-app APIのURLを入力してください:", window.apiClient.defaultApiUrl);
  if (url?.trim()) {
    chrome.storage.local.set({ visaAppApiUrl: url.trim() });
    setCaseListStatus("API URL を保存しました。必要なら案件一覧を更新してください");
    setStatus("API URL を保存しました");
  }
});

elements.loadFromApi.addEventListener("click", async () => {
  const requestedCase = getRequestedCase();
  if (!requestedCase) {
    setStatus("案件一覧から選択するか case_id を入力してください");
    return;
  }

  resetWorkflowBanners();

  try {
    setStatus("visa-app から取得中...");
    const applicationData = await window.apiClient.getApplicationData(requestedCase.caseId);

    const workflowState = applicationData.workflow_state;
    const displayState = toWorkflowDisplayState(workflowState);
    elements.workflowState.textContent = workflowStateLabel[displayState];
    if (applicationData.fillable) {
      elements.workflowReady.hidden = false;
    } else {
      elements.workflowWarning.hidden = false;
    }

    const rows = applicationData.rows || [];
    if (!rows.length) {
      await clearRows("入力対象の値がありません。visa-app のレビュー内容を確認してください。");
      return;
    }

    const sourceLabel = getCaseSourceLabel(requestedCase.caseId, requestedCase.caseSummary);
    const warningText = (applicationData.warnings || []).join("\n");
    await saveRows(rows, sourceLabel, applicationData.fillable);
    await chrome.storage.local.set({ visaSelectedCaseId: requestedCase.caseSummary ? requestedCase.caseId : "" });

    if (warningText) {
      setStatus(`${sourceLabel}\n${rows.length}件の入力値を保存しました\n${warningText}`);
    }
  } catch (error) {
    await clearRows(`読込エラー\n${error.message}`);
  }
});

async function initializePopup() {
  const { visaRows, visaDataSource, visaFillable } = await chrome.storage.local.get([
    "visaRows",
    "visaDataSource",
    "visaFillable",
  ]);

  if (visaRows?.length) {
    setFillButtonsEnabled(Boolean(visaFillable));
    setStatus(`${visaDataSource || "保存済みデータ"}\n${visaRows.length}件の入力値が保存されています`);
  } else {
    setFillButtonsEnabled(false);
  }

  await loadCases();
}

initializePopup();
