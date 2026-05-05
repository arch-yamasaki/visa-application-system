function normalize(value) {
  return String(value || "")
    .replace(/\s+/g, "")
    .replace(/[‐-‒–—―ー－]/g, "-")
    .toLowerCase();
}

function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}

function visible(element) {
  const style = window.getComputedStyle(element);
  return style.display !== "none" && style.visibility !== "hidden";
}

function eventInput(element) {
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  element.dispatchEvent(new Event("blur", { bubbles: true }));
}

function byId(id) {
  return id ? document.getElementById(id) : null;
}

function byName(name) {
  if (!name) return [];
  return Array.from(document.querySelectorAll(`[name="${cssEscape(name)}"]`));
}

function rowContainer(element) {
  return element?.closest("dl, tr, .c-input, .form-group, fieldset, section, div") || null;
}

function textForControl(element) {
  const id = element.id;
  const label = id ? document.querySelector(`label[for="${cssEscape(id)}"]`) : null;
  const row = rowContainer(element);
  return `${label?.innerText || ""} ${row?.innerText || ""} ${element.value || ""}`;
}

function findByLabel(row, selector = "input[name], input[id], select[name], select[id], textarea[name], textarea[id]") {
  const wanted = normalize(row.label);
  if (!wanted) return null;

  const controls = Array.from(document.querySelectorAll(selector));
  const scored = controls
    .map((element) => {
      const text = normalize(textForControl(element));
      if (!text) return null;
      if (text.includes(wanted) || wanted.includes(text.slice(0, 20))) return { element, score: text.includes(wanted) ? 2 : 1 };
      return null;
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score);

  return scored[0]?.element || null;
}

function chooseSelect(select, rawValue) {
  if (!select?.options) return false;
  const wanted = normalize(rawValue);
  const options = Array.from(select.options);
  const exact = options.find((option) => normalize(option.textContent) === wanted || normalize(option.value) === wanted);
  const partial = options.find((option) => {
    const text = normalize(option.textContent);
    return text.includes(wanted) || wanted.includes(text);
  });
  const option = exact || partial;
  if (!option) return false;
  select.value = option.value;
  eventInput(select);
  return true;
}

function chooseRadioOrCheckbox(elements, rawValue) {
  const wanted = normalize(rawValue);
  const candidates = elements.filter((element) => element.type === "radio" || element.type === "checkbox");
  const target = candidates.find((element) => {
    if (["true", "1", "checked", "確認済み"].includes(wanted) && element.type === "checkbox") return true;
    const text = normalize(textForControl(element));
    return normalize(element.value) === wanted || text.includes(wanted) || wanted.includes(text);
  });

  if (!target) return false;
  if (target.type === "checkbox") {
    target.checked = true;
  } else {
    target.click();
  }
  eventInput(target);
  return true;
}

function fillText(element, value) {
  element.focus();
  element.value = value;
  eventInput(element);
  return true;
}

function targetForRow(row) {
  const expectedType = (row.input_type || "").toLowerCase();
  const idElement = byId(row.field_id);
  const named = byName(row.field_name);

  if (expectedType === "select") {
    return (
      (idElement?.tagName === "SELECT" ? idElement : null) ||
      named.find((element) => element.tagName === "SELECT" && visible(element)) ||
      named.find((element) => element.tagName === "SELECT") ||
      findByLabel(row, "select[name], select[id]")
    );
  }

  return idElement || named.find(visible) || named[0] || findByLabel(row);
}

function fillRow(row) {
  const value = (row.fill_value || row.display_value || "").trim();
  if (!value || row.input_type === "file") return { status: "skipped", reason: "empty-or-file" };

  const idElement = byId(row.field_id);
  const named = byName(row.field_name);
  const expectedType = (row.input_type || "").toLowerCase();

  if (expectedType === "select") {
    const select =
      (idElement?.tagName === "SELECT" ? idElement : null) ||
      named.find((element) => element.tagName === "SELECT" && visible(element)) ||
      named.find((element) => element.tagName === "SELECT") ||
      findByLabel(row, "select[name], select[id]");

    if (!select) return { status: "missed", reason: "select-not-found" };
    return chooseSelect(select, value) ? { status: "filled" } : { status: "missed", reason: "option-not-found" };
  }

  const primary = idElement || named.find(visible) || named[0] || findByLabel(row);
  const elements = named.length ? named : primary ? [primary] : [];

  if (!primary && !elements.length) return { status: "missed", reason: "element-not-found" };

  const type = expectedType || primary?.tagName.toLowerCase() || "";
  if (type === "select" || primary?.tagName === "SELECT") {
    return chooseSelect(primary, value) ? { status: "filled" } : { status: "missed", reason: "option-not-found" };
  }

  if (type === "radio" || type === "checkbox" || primary?.type === "radio" || primary?.type === "checkbox") {
    return chooseRadioOrCheckbox(elements.length ? elements : [primary], value)
      ? { status: "filled" }
      : { status: "missed", reason: "choice-not-found" };
  }

  if (primary?.tagName === "TEXTAREA" || primary?.tagName === "INPUT") {
    return fillText(primary, value) ? { status: "filled" } : { status: "missed", reason: "text-fill-failed" };
  }

  return { status: "missed", reason: "unsupported-element" };
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function randomDelay(min, max) {
  return Math.floor(min + Math.random() * (max - min + 1));
}

function ensureAgentStyle() {
  if (document.getElementById("visa-autofill-agent-style")) return;

  const style = document.createElement("style");
  style.id = "visa-autofill-agent-style";
  style.textContent = `
    .visa-autofill-highlight-running {
      outline: 3px solid #2f6fed !important;
      outline-offset: 2px !important;
      box-shadow: 0 0 0 6px rgba(47, 111, 237, 0.18) !important;
      transition: outline-color 160ms ease, box-shadow 160ms ease !important;
    }
    .visa-autofill-highlight-filled {
      outline: 3px solid #1f9d55 !important;
      outline-offset: 2px !important;
      box-shadow: 0 0 0 6px rgba(31, 157, 85, 0.16) !important;
      transition: outline-color 160ms ease, box-shadow 160ms ease !important;
    }
    .visa-autofill-highlight-missed {
      outline: 3px solid #d94d2b !important;
      outline-offset: 2px !important;
      box-shadow: 0 0 0 6px rgba(217, 77, 43, 0.14) !important;
      transition: outline-color 160ms ease, box-shadow 160ms ease !important;
    }
    #visa-autofill-agent-panel {
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 2147483647;
      width: min(320px, calc(100vw - 36px));
      border: 1px solid #b8c2d6;
      border-radius: 8px;
      background: #ffffff;
      color: #172033;
      box-shadow: 0 12px 30px rgba(23, 32, 51, 0.18);
      font: 13px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      padding: 12px;
    }
    #visa-autofill-agent-panel strong {
      display: block;
      margin-bottom: 6px;
      font-size: 14px;
    }
    #visa-autofill-agent-panel .visa-autofill-agent-label {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #40506a;
    }
    #visa-autofill-agent-panel progress {
      width: 100%;
      height: 8px;
      margin-top: 8px;
      vertical-align: top;
    }
  `;
  document.documentElement.append(style);
}

function agentPanel() {
  ensureAgentStyle();
  let panel = document.getElementById("visa-autofill-agent-panel");
  if (panel) return panel;

  panel = document.createElement("div");
  panel.id = "visa-autofill-agent-panel";
  panel.innerHTML = `
    <strong>AI Agent入力中</strong>
    <div class="visa-autofill-agent-count"></div>
    <div class="visa-autofill-agent-label"></div>
    <progress value="0" max="1"></progress>
  `;
  document.documentElement.append(panel);
  return panel;
}

function updateAgentPanel({ current, total, label, done = false }) {
  const panel = agentPanel();
  panel.querySelector("strong").textContent = done ? "AI Agent入力完了" : "AI Agent入力中";
  panel.querySelector(".visa-autofill-agent-count").textContent = `${current} / ${total}`;
  panel.querySelector(".visa-autofill-agent-label").textContent = label || "";
  const progress = panel.querySelector("progress");
  progress.max = Math.max(total, 1);
  progress.value = Math.min(current, total);
}

function clearHighlight(element) {
  if (!element) return;
  element.classList.remove(
    "visa-autofill-highlight-running",
    "visa-autofill-highlight-filled",
    "visa-autofill-highlight-missed"
  );
}

function highlightElement(element, status) {
  if (!element) return;
  ensureAgentStyle();
  clearHighlight(element);
  element.classList.add(`visa-autofill-highlight-${status}`);
}

function maskedValue(value) {
  if (!value) return "";
  return `[masked:${String(value).length}]`;
}

function resultSummary(results) {
  const filled = results.filter(({ result }) => result.status === "filled").length;
  const skipped = results.filter(({ result }) => result.status === "skipped").length;
  const missed = results.filter(({ result }) => result.status === "missed");

  console.table(results.map(({ row, result }) => ({
    label: row.label,
    value: maskedValue(row.fill_value),
    status: result.status,
    reason: result.reason || ""
  })));

  return `入力完了: ${filled}件入力、${skipped}件スキップ、${missed.length}件未検出。詳細はDevTools consoleを確認してください。`;
}

function previewRows(rows) {
  const results = rows.map((row) => {
    const element = targetForRow(row);
    return {
      label: row.label,
      value: maskedValue(row.fill_value),
      target: element ? `${element.tagName.toLowerCase()}#${element.id || ""}[name="${element.name || ""}"]` : "",
      status: element ? "found" : "missed"
    };
  });
  console.table(results);
  const found = results.filter((row) => row.status === "found").length;
  return `入力対象確認: ${found}/${results.length}件見つかりました。詳細はDevTools consoleを確認してください。`;
}

function fillRows(rows) {
  const results = rows.map((row) => {
    try {
      return { row, result: fillRow(row) };
    } catch (error) {
      return { row, result: { status: "missed", reason: error.message || "unexpected-error" } };
    }
  });
  return resultSummary(results);
}

async function fillRowsProgressively(rows) {
  const results = [];
  let previousElement = null;

  for (const [index, row] of rows.entries()) {
    const current = index + 1;
    const element = targetForRow(row);
    clearHighlight(previousElement);
    previousElement = element;
    updateAgentPanel({ current, total: rows.length, label: row.label });

    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      highlightElement(element, "running");
    }

    await sleep(randomDelay(350, 900));

    let result;
    try {
      result = fillRow(row);
    } catch (error) {
      result = { status: "missed", reason: error.message || "unexpected-error" };
    }

    results.push({ row, result });
    if (element) highlightElement(element, result.status === "filled" ? "filled" : "missed");
    await sleep(randomDelay(180, 420));
  }

  updateAgentPanel({ current: rows.length, total: rows.length, label: "完了", done: true });
  window.setTimeout(() => clearHighlight(previousElement), 1400);
  return resultSummary(results);
}

var VISA_AUTOFILL_CONTENT_VERSION = "0.2.0";

if (window.__visaAutofillContentHandler) {
  chrome.runtime.onMessage.removeListener(window.__visaAutofillContentHandler);
}

window.__visaAutofillContentInstalled = true;
window.__visaAutofillContentVersion = VISA_AUTOFILL_CONTENT_VERSION;
window.__visaAutofillContentHandler = (message, _sender, sendResponse) => {
    if (message.type === "VISA_AUTOFILL_PREVIEW") {
      sendResponse({ message: previewRows(message.rows || []) });
      return true;
    }
    if (message.type === "VISA_AUTOFILL_FILL") {
      sendResponse({ message: fillRows(message.rows || []) });
      return true;
    }
    if (message.type === "VISA_AUTOFILL_FILL_PROGRESSIVE") {
      fillRowsProgressively(message.rows || []).then((messageText) => {
        sendResponse({ message: messageText });
      });
      return true;
    }
    return false;
};

chrome.runtime.onMessage.addListener(window.__visaAutofillContentHandler);
