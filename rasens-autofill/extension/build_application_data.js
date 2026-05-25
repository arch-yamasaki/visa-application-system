/**
 * Build Chrome-extension autofill rows from canonical case data.
 * Vanilla JS port of rasens-autofill/scripts/build_application_data.py.
 * ES2020 — runs in Chrome extension context.
 */

/**
 * Traverse a nested object by dot-separated path.
 * Supports array indices (e.g. "education.0.school_name").
 * @param {object} data
 * @param {string} path
 * @returns {*}
 */
function getByPath(data, path) {
  let current = data;
  for (const part of path.split(".")) {
    if (current == null) return undefined;
    if (Array.isArray(current)) {
      const index = Number(part);
      if (!Number.isInteger(index) || index < 0) return undefined;
      current = current[index];
    } else if (typeof current === "object") {
      current = current[part];
    } else {
      return undefined;
    }
  }
  return current;
}

/**
 * Extract digits from a value and return the first `digits` characters.
 * @param {*} value
 * @param {number} digits
 * @returns {string}
 */
function dateDigits(value, digits) {
  const raw = String(value ?? "");
  const joined = raw.match(/\d+/g)?.join("") ?? "";
  return joined.slice(0, digits);
}

/**
 * Apply a named transform to a value.
 * @param {*} value
 * @param {string} transform
 * @returns {string}
 */
function transformValue(value, transform) {
  if (value == null) return "";
  const rawValue = String(value).trim();
  if (["unknown", "not_applicable", "n/a", "na"].includes(rawValue.toLowerCase())) {
    return "";
  }
  switch (transform) {
    case "date_yyyymmdd":
      return dateDigits(value, 8);
    case "date_yyyymm":
      return dateDigits(value, 6);
    case "boolean_yes_no": {
      const truthy = [true, "true", "yes", "有", "あり", 1, "1"];
      return truthy.includes(typeof value === "string" ? value.toLowerCase() : value)
        ? "有 Yes"
        : "無 No";
    }
    case "marital_yes_no":
      return value === "married" ? "有 Married" : "無 Single";
    case "sex_ja": {
      const map = { male: "男 Male", female: "女 Female" };
      return map[String(value)] ?? String(value);
    }
    default:
      return String(value);
  }
}

/**
 * Evaluate visible_when conditions for a mapping item.
 * @param {object} caseData
 * @param {object} item - mapping entry with optional visible_when array
 * @returns {boolean}
 */
function isVisible(caseData, item) {
  const conditions = item.visible_when;
  if (!conditions?.length) return true;
  for (const condition of conditions) {
    const actual = getByPath(caseData, condition.path);
    const operator = condition.operator ?? "==";
    const expected = condition.value;
    if (operator === "==" && actual !== expected) return false;
    if (operator === "!=" && actual === expected) return false;
  }
  return true;
}

/**
 * Build autofill rows from case data and mapping definition.
 * @param {object} caseData
 * @param {object} mappingData - parsed rasens_offer_mapping.json
 * @returns {Array<object>}
 */
function buildRows(caseData, mappingData) {
  const rows = [];
  for (const item of mappingData.mappings ?? []) {
    if (!isVisible(caseData, item)) continue;
    const value = getByPath(caseData, item.value_path);
    const fillValue = transformValue(value, item.transform ?? "");
    if (fillValue === "") continue;
    rows.push({
      section: item.section ?? "",
      no: item.form_item_no ?? "",
      label: item.label ?? item.canonical_id,
      field_name: item.field_name ?? "",
      field_id: item.field_id ?? "",
      input_type: item.input_type ?? "text",
      display_value: fillValue,
      fill_value: fillValue,
      source_page: "case_data",
      confidence: caseData?.case?.case_id?.startsWith("demo-") ? "demo" : "generated",
      canonical_id: item.canonical_id,
      notes: "generated from canonical case_data",
    });
  }
  return rows;
}

// Export for use by popup.js
window.buildApplicationData = { getByPath, transformValue, isVisible, buildRows };
