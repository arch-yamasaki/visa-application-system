"""Generate RASENS application-data rows from canonical case_data."""

from __future__ import annotations

import os
import json
import copy
import re
from pathlib import Path
from typing import Any


EMPTY_STRINGS = {"unknown", "not_applicable", "n/a", "na"}
FILLABLE_WORKFLOW_STATES = {"extracted", "needs_review", "ready_to_fill"}
BOOLEAN_PATHS = (
    "applicant.family.has_accompanying_members",
    "applicant.family.has_japan_relatives_or_cohabitants",
    "applicant.family.japan_relatives_or_cohabitants.0.will_cohabit",
    "applicant.family.japan_relatives_or_cohabitants.1.will_cohabit",
    "applicant.family.japan_relatives_or_cohabitants.2.will_cohabit",
    "applicant.has_employment_history",
    "applicant.employment_history.0.start_month_unknown",
    "applicant.employment_history.0.end_month_unknown",
    "applicant.employment_history.1.start_month_unknown",
    "applicant.employment_history.1.end_month_unknown",
    "applicant.employment_history.2.start_month_unknown",
    "applicant.employment_history.2.end_month_unknown",
    "applicant.immigration_history.has_entries",
    "applicant.immigration_history.prior_coe_applications.has_history",
    "applicant.immigration_history.criminal_record",
    "applicant.immigration_history.deportation_or_departure_order",
    "applicant.qualifications.it.has_qualification",
    "employer.has_corporate_number",
    "employment.has_position",
)
TOKYO_AREA_PREFECTURES = ("東京都", "神奈川県", "埼玉県", "千葉県")
NARITA_AREA_PREFECTURES = ("茨城県", "栃木県", "群馬県", "山梨県", "長野県", "新潟県")
CHUBU_AREA_PREFECTURES = ("愛知県", "岐阜県", "三重県", "静岡県")
KANSAI_AREA_PREFECTURES = ("大阪府", "京都府", "兵庫県", "奈良県", "和歌山県", "滋賀県")
HIROSHIMA_AREA_PREFECTURES = ("広島県", "岡山県", "山口県", "鳥取県", "島根県")
FUKUOKA_AREA_PREFECTURES = ("福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県")
VISA_APPLICATION_LOCATIONS = (
    (("ネパール", "nepal"), "Kathmandu"),
    (("ベトナム", "viet nam", "vietnam"), "Hanoi"),
    (("フィリピン", "philippines"), "Manila"),
    (("インドネシア", "indonesia"), "Jakarta"),
    (("中国", "china"), "Beijing"),
    (("韓国", "korea"), "Seoul"),
    (("ミャンマー", "myanmar"), "Yangon"),
    (("米国", "united states", "usa"), "United States"),
)


def get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, list):
            index = int(part)
            current = current[index]
        else:
            current = current[part]
    return current


def has_path(data: dict[str, Any], path: str) -> bool:
    try:
        get_path(data, path)
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    return True


def date_digits(value: Any, digits: int) -> str:
    groups = re.findall(r"\d+", str(value))
    joined = "".join(groups)
    if groups and len(groups[0]) == 4:
        if digits == 8 and len(groups) >= 3:
            return f"{int(groups[0]):04d}{int(groups[1]):02d}{int(groups[2]):02d}"
        if digits == 6 and len(groups) >= 2:
            return f"{int(groups[0]):04d}{int(groups[1]):02d}"
    return joined[:digits]


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return not stripped or stripped.lower() in EMPTY_STRINGS
    return False


def is_fillable_workflow_state(workflow_state: str) -> bool:
    return workflow_state in FILLABLE_WORKFLOW_STATES


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"true", "yes", "有", "あり", "有 yes", "1"}
    return False


def transform_value(value: Any, transform: str = "") -> str:
    if is_empty_value(value):
        return ""
    if transform == "date_yyyymmdd":
        return date_digits(value, 8)
    if transform == "date_yyyymm":
        return date_digits(value, 6)
    if transform == "date_yyyy":
        return date_digits(value, 4)
    if transform == "digits":
        return "".join(re.findall(r"\d+", str(value)))
    if transform == "zero_to_empty":
        return "" if str(value).strip() in {"0", "0.0"} else str(value).strip()
    if transform == "boolean_yes_no":
        return "有 Yes" if truthy(value) else "無 No"
    if transform == "month_unknown":
        return "月不詳 Unknown(Month)" if truthy(value) else "不明な点は無い No unclear points"
    if transform == "marital_yes_no":
        return "有 Married" if value == "married" else "無 Single"
    if transform == "sex_ja":
        return {"male": "男 Male", "female": "女 Female"}.get(str(value), str(value))
    if transform == "contract_type":
        normalized = str(value).strip().lower()
        if normalized in {"employment", "雇用", "employee", "fixed term contract employee"}:
            return "雇用 Employment"
        if "社員" in normalized or "employee" in normalized or "employment" in normalized:
            return "雇用 Employment"
        if normalized in {"entrustment", "委任"}:
            return "委任 Entrustment"
        if normalized in {"service_contract", "service contract", "請負"}:
            return "請負 Service contract"
        if "請負" in normalized or "service contract" in normalized:
            return "請負 Service contract"
        if normalized in {"other", "others", "その他"}:
            return "その他 Others"
    if transform == "employment_period_type":
        normalized = str(value).strip().lower()
        if "なし" in normalized or "non" in normalized or "no fixed" in normalized:
            return "定めなし Non-Fixed"
        return "定めあり Fixed"
    if transform == "industry_primary":
        return infer_industry_primary({"employer": {"industry_primary": value}}) or str(value).strip()
    if transform == "education_country":
        return infer_education_country(str(value))
    if transform == "education_level":
        return infer_education_level(str(value))
    if transform == "major_field_university":
        return infer_major_field_university(str(value))
    return str(value).strip()


def ensure_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        value = {}
        data[key] = value
    return value


def set_default_from(data: dict[str, Any], target_path: str, source_path: str) -> None:
    if has_path(data, source_path):
        value = get_path(data, source_path)
        if not is_empty_value(value):
            set_default(data, target_path, value)


def set_default(data: dict[str, Any], path: str, value: Any) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        current = ensure_dict(current, part)
    if is_empty_value(current.get(parts[-1])):
        current[parts[-1]] = value


def normalize_bool_path(data: dict[str, Any], path: str) -> None:
    if has_path(data, path):
        parent: Any = data
        parts = path.split(".")
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        last = parts[-1]
        value = parent[int(last)] if isinstance(parent, list) else parent.get(last)
        if not isinstance(value, bool) and not is_empty_value(value):
            if isinstance(parent, list):
                parent[int(last)] = truthy(value)
            else:
                parent[last] = truthy(value)


def infer_planned_port(source_data: dict[str, Any]) -> str:
    employer = source_data.get("employer", {})
    address = str(employer.get("address") or "")
    if any(prefecture in address for prefecture in TOKYO_AREA_PREFECTURES):
        return "羽田空港(HND) Haneda Airport"
    if any(prefecture in address for prefecture in NARITA_AREA_PREFECTURES):
        return "成田空港(NRT) Narita International Airport"
    if "北海道" in address:
        return "新千歳空港(CTS) New Chitose Airport"
    if any(prefecture in address for prefecture in CHUBU_AREA_PREFECTURES):
        return "中部国際空港(NGO) Chubu Centrair International Airport"
    if any(prefecture in address for prefecture in KANSAI_AREA_PREFECTURES):
        return "関西国際空港(KIX) Kansai International Airport"
    if any(prefecture in address for prefecture in HIROSHIMA_AREA_PREFECTURES):
        return "広島空港(HIJ) Hiroshima Airport"
    if any(prefecture in address for prefecture in FUKUOKA_AREA_PREFECTURES):
        return "福岡空港(FUK) Fukuoka Airport"
    return "成田空港(NRT) Narita International Airport"


def infer_industry_primary(source_data: dict[str, Any]) -> str:
    employer = source_data.get("employer", {})
    text = " ".join(str(employer.get(key) or "") for key in ("industry_primary", "industry_other", "name"))
    if "建設" in text or "construction" in text.lower():
        return "建設業 Construction"
    if "不動産" in text or "real estate" in text.lower():
        return "不動産・物品賃貸業 Real estate and goods rental"
    if "情報" in text or "communication" in text.lower() or "software" in text.lower():
        return "情報通信業 Information and communication industry"
    return ""


def infer_education_country(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        return ""
    japanese_school_markers = (
        "東京", "大阪", "京都", "北海道", "東北", "名古屋", "九州", "筑波", "早稲田", "慶應",
        "tokyo", "osaka", "kyoto", "hokkaido", "tohoku", "nagoya", "kyushu", "tsukuba", "waseda", "keio",
    )
    if "日本" in normalized or "本邦" in normalized or "japan" in normalized:
        return "本邦 Japan"
    if any(marker in normalized for marker in japanese_school_markers):
        return "本邦 Japan"
    return "外国 Foreign country"


def infer_education_level(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        return ""
    if "博士" in normalized or "doctor" in normalized or "phd" in normalized:
        return "大学院（博士） Doctor"
    if "修士" in normalized or "master" in normalized:
        return "大学院（修士） Master"
    if "大学" in normalized or "university" in normalized or "bachelor" in normalized or "学士" in normalized:
        return "大学 Bachelor"
    if "短期" in normalized or "junior college" in normalized:
        return "短期大学 Junior college"
    if "専門" in normalized or "vocational" in normalized or "college of technology" in normalized:
        return "専門学校 College of technology"
    if "高等" in normalized or "high school" in normalized or "senior" in normalized:
        return "高等学校 Senior high school"
    if "中学" in normalized or "junior high" in normalized:
        return "中学校 Junior high school"
    return "その他 Others"


def infer_major_field_university(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        return ""
    if "工学" in normalized or "engineer" in normalized or "engineering" in normalized or "architect" in normalized:
        return "工学 Engineer"
    if "法学" in normalized or "law" in normalized:
        return "法学 Law"
    if "経済" in normalized or "econom" in normalized:
        return "経済学 Econom"
    if "経営" in normalized or "business" in normalized:
        return "経営学 Business administration"
    if "語学" in normalized or "linguist" in normalized:
        return "語学 Linguistics"
    if "情報" in normalized or "computer" in normalized:
        return "工学 Engineer"
    return value.strip()


def infer_visa_application_location(source_data: dict[str, Any]) -> str:
    applicant = source_data.get("applicant", {})
    text = " ".join(
        str(applicant.get(key) or "") for key in ("nationality_region", "home_country_address")
    ).lower()
    for keywords, location in VISA_APPLICATION_LOCATIONS:
        if any(keyword.lower() in text for keyword in keywords):
            return location
    return ""


def apply_application_defaults(source_data: dict[str, Any]) -> None:
    for path in BOOLEAN_PATHS:
        normalize_bool_path(source_data, path)

    set_default(source_data, "entry_plan.planned_port", infer_planned_port(source_data))
    set_default(source_data, "entry_plan.planned_period_years", "5")
    set_default(source_data, "entry_plan.planned_period_months", "0")
    visa_location = infer_visa_application_location(source_data)
    if visa_location:
        set_default(source_data, "entry_plan.visa_application_location", visa_location)
    set_default(source_data, "applicant.family.has_accompanying_members", False)
    set_default(source_data, "applicant.family.has_japan_relatives_or_cohabitants", False)
    set_default(source_data, "applicant.has_employment_history", False)
    set_default(source_data, "applicant.immigration_history.has_entries", False)
    set_default(source_data, "applicant.immigration_history.prior_coe_applications.has_history", False)
    set_default(source_data, "applicant.immigration_history.criminal_record", False)
    set_default(source_data, "applicant.immigration_history.deportation_or_departure_order", False)
    set_default(source_data, "employment.contract_type", "雇用 Employment")
    set_default(source_data, "employment.employment_period_type", "定めあり Fixed")
    set_default(source_data, "employment.employment_period_years", "1")
    set_default(source_data, "employment.employment_period_months", "0")

    employer = ensure_dict(source_data, "employer")
    if is_empty_value(employer.get("has_corporate_number")):
        employer["has_corporate_number"] = not is_empty_value(employer.get("corporate_number"))
    if is_empty_value(employer.get("industry_primary")):
        industry = infer_industry_primary(source_data)
        if industry:
            employer["industry_primary"] = industry

    education = source_data.get("applicant", {}).get("education")
    if isinstance(education, list) and education:
        first_education = education[0]
        if isinstance(first_education, dict):
            if is_empty_value(first_education.get("major_field")) and not is_empty_value(first_education.get("major")):
                first_education["major_field"] = first_education["major"]
            if is_empty_value(first_education.get("country_type")):
                first_education["country_type"] = infer_education_country(
                    str(first_education.get("school_name") or first_education.get("level") or "")
                )
            if is_empty_value(first_education.get("level")) and not is_empty_value(first_education.get("level_detail")):
                first_education["level"] = infer_education_level(str(first_education["level_detail"]))
            if not is_empty_value(first_education.get("level")):
                first_education["level"] = infer_education_level(str(first_education["level"]))
            if not is_empty_value(first_education.get("major_field")):
                first_education["major_field"] = infer_major_field_university(str(first_education["major_field"]))

    set_default_from(source_data, "proxy.name", "employer.name")
    set_default(source_data, "proxy.relationship", "所属機関等契約先")
    set_default_from(source_data, "proxy.postal_code", "employer.postal_code")
    set_default_from(source_data, "proxy.address", "employer.address")
    set_default_from(source_data, "proxy.phone", "employer.phone")


def load_default_settings() -> dict[str, Any]:
    intermediary = {
        "name": os.environ.get("INTERMEDIARY_NAME", ""),
        "postal_code": os.environ.get("INTERMEDIARY_POSTAL_CODE", ""),
        "address": os.environ.get("INTERMEDIARY_ADDRESS", ""),
        "organization": os.environ.get("INTERMEDIARY_ORGANIZATION", ""),
        "phone": os.environ.get("INTERMEDIARY_PHONE", ""),
    }
    if any(not is_empty_value(value) for value in intermediary.values()):
        return {"intermediary": intermediary}
    return {}


def visible(case_data: dict[str, Any], mapping_item: dict[str, Any]) -> bool:
    for condition in mapping_item.get("visible_when", []):
        if not has_path(case_data, condition["path"]):
            return False
        actual = get_path(case_data, condition["path"])
        expected = condition.get("value")
        operator = condition.get("operator", "==")
        if isinstance(expected, bool):
            actual = truthy(actual)
        if operator == "==" and actual != expected:
            return False
        if operator == "!=" and actual == expected:
            return False
    return True


BACKEND_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BACKEND_DIR.parents[1] if len(BACKEND_DIR.parents) > 1 else BACKEND_DIR


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_mapping_path() -> Path:
    env_path = os.environ.get("RASENS_MAPPING_PATH")
    if env_path:
        return Path(env_path)
    workspace_path = WORKSPACE_DIR / "rasens-autofill/data/mappings/rasens_offer_mapping_v2.json"
    if workspace_path.exists():
        return workspace_path
    return BACKEND_DIR / "data/mappings/rasens_offer_mapping_v2.json"


def default_form_definitions_path() -> Path | None:
    env_path = os.environ.get("RASENS_FORM_DEFINITIONS_PATH")
    if env_path:
        return Path(env_path)
    workspace_path = WORKSPACE_DIR / "rasens-autofill/data/form_definitions/rasens_offer_fields.json"
    if workspace_path.exists():
        return workspace_path
    backend_path = BACKEND_DIR / "data/form_definitions/rasens_offer_fields.json"
    if backend_path.exists():
        return backend_path
    return None


def load_default_mapping() -> dict[str, Any]:
    return load_json(default_mapping_path())


def load_default_form_definitions() -> dict[str, Any]:
    path = default_form_definitions_path()
    if path is None:
        return {}
    return load_json(path)


def _field_controls(
    form_definitions: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    controls: dict[tuple[str, str], dict[str, Any]] = {}
    fields = form_definitions.get("fields", [])
    for index, field in enumerate(fields, start=1):
        for control in field.get("controls", []):
            key = (control.get("field_id", ""), control.get("field_name", ""))
            controls[key] = {
                "section": field.get("section", ""),
                "form_order": index,
                "display_no": field.get("no", ""),
                "label": field.get("label", ""),
                "required": field.get("required", False),
                "input_type": control.get("input_type", ""),
            }
    if fields:
        return controls

    for index, item in enumerate(mapping.get("mappings", []), start=1):
        key = (item.get("field_id", ""), item.get("field_name", ""))
        controls[key] = {
            "section": item.get("section", ""),
            "form_order": item.get("form_order", index),
            "display_no": item.get("display_no") or item.get("form_item_no", ""),
            "label": item.get("label", item.get("canonical_id", "")),
            "required": item.get("required", False),
            "input_type": item.get("input_type", ""),
        }
    return controls


def _field_info(
    mapping_item: dict[str, Any],
    controls: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    field_id = mapping_item.get("field_id", "")
    field_name = mapping_item.get("field_name", "")
    info = controls.get((field_id, field_name))
    if info is None:
        raise ValueError(f"mapping target not found: {field_id or field_name}")
    if mapping_item.get("input_type") and mapping_item["input_type"] != info["input_type"]:
        raise ValueError(f"input_type mismatch: {mapping_item.get('canonical_id')}")
    return info


def build_rows(
    case_data: dict[str, Any],
    mapping: dict[str, Any],
    form_definitions: dict[str, Any],
) -> list[dict[str, Any]]:
    controls = _field_controls(form_definitions, mapping)
    rows: list[dict[str, Any]] = []

    for item in mapping.get("mappings", []):
        if not visible(case_data, item):
            continue

        value_path = item.get("value_path", "")
        if value_path and not has_path(case_data, value_path):
            continue

        raw_value = get_path(case_data, value_path) if value_path else item.get("fixed_value")
        fill_value = transform_value(raw_value, item.get("transform", ""))
        if fill_value == "":
            continue

        info = _field_info(item, controls)
        rows.append(
            {
                "section": info["section"],
                "form_order": info["form_order"],
                "display_no": info["display_no"],
                "label": item.get("label") or info["label"],
                "canonical_path": value_path,
                "source_paths": [value_path] if value_path else [],
                "field_name": item.get("field_name", ""),
                "field_id": item.get("field_id", ""),
                "input_type": item.get("input_type") or info["input_type"],
                "display_value": str(raw_value).strip(),
                "fill_value": fill_value,
                "source_page": item.get("source_page", "case_data"),
                "confidence": item.get("confidence", "generated"),
                "required": info["required"],
                "manual_required": item.get("manual_required", False),
                "notes": item.get("notes", ""),
            }
        )

    return rows


def build_application_data(
    case_doc: dict[str, Any],
    mapping: dict[str, Any],
    form_definitions: dict[str, Any],
) -> dict[str, Any]:
    case_data = case_doc.get("case_data", {})
    settings = case_doc.get("settings") or case_data.get("settings") or load_default_settings()
    source_data = copy.deepcopy(case_data)
    if settings:
        source_data["settings"] = settings
    apply_application_defaults(source_data)
    workflow_state = case_doc.get("workflow_state") or case_data.get("case", {}).get("workflow_state", "")
    rows = build_rows(source_data, mapping, form_definitions)
    fillable = is_fillable_workflow_state(workflow_state)
    warnings = [] if fillable else [f"workflow_state is not fillable: {workflow_state or 'unknown'}"]

    return {
        "schema_version": "1.0",
        "case_id": case_doc.get("case_id") or case_data.get("case", {}).get("case_id", ""),
        "workflow_state": workflow_state,
        "fillable": fillable,
        "mapping_version": mapping.get("schema_version", ""),
        "form_definition": mapping.get("form_definition") or form_definitions.get("source_file", ""),
        "warnings": warnings,
        "summary": {
            "rows_total": len(rows),
            "rows_fillable": len([row for row in rows if row["fill_value"]]),
            "rows_skipped_empty": len(mapping.get("mappings", [])) - len(rows),
            "manual_required": len([row for row in rows if row["manual_required"]]),
        },
        "rows": rows,
    }


def build_display_case_data(
    case_data: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return case_data with deterministic display/fill defaults applied."""
    display_data = copy.deepcopy(case_data)
    display_settings = settings or display_data.get("settings") or load_default_settings()
    if display_settings:
        display_data["settings"] = copy.deepcopy(display_settings)
    apply_application_defaults(display_data)
    return display_data
