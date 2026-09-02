"""Generate RASENS application-data rows from canonical case_data."""

from __future__ import annotations

import os
import copy
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from rasens_definitions import (
    default_form_definitions_path,
    default_mapping_path,
    load_default_form_definitions,
    load_default_mapping,
    load_json,
)


EMPTY_STRINGS = {"unknown", "not_applicable", "n/a", "na"}
FILLABLE_WORKFLOW_STATES = {"extracted", "needs_review", "ready_to_fill"}
INTERMEDIARY_ENV_VARS = {
    "name": "INTERMEDIARY_NAME",
    "postal_code": "INTERMEDIARY_POSTAL_CODE",
    "address": "INTERMEDIARY_ADDRESS",
    "organization": "INTERMEDIARY_ORGANIZATION",
    "phone": "INTERMEDIARY_PHONE",
}
INTERMEDIARY_PATHS = tuple(
    f"settings.intermediary.{field}"
    for field in INTERMEDIARY_ENV_VARS
)
RECEIVING_PATHS = (
    "settings.receiving_method.notification_email",
)
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
)
NATIONALITY_REGION_VALUES = (
    (("中国", "china", "people's republic of china", "prc"), "中国 People's Republic of China"),
    (("ベトナム", "viet nam", "vietnam"), "ベトナム Viet Nam"),
    (("韓国", "korea", "republic of korea", "south korea"), "韓国 Republic of Korea"),
    (("フィリピン", "philippines"), "フィリピン Philippines"),
    (("ブラジル", "brazil"), "ブラジル Brazil"),
    (("ネパール", "nepal"), "ネパール Nepal"),
    (("インドネシア", "indonesia"), "インドネシア Indonesia"),
    (("ミャンマー", "myanmar"), "ミャンマー Myanmar"),
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
    normalized = unicodedata.normalize("NFKC", str(value))
    groups = re.findall(r"\d+", normalized)
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


def annual_sales_jpy(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).replace(",", "")
    normalized = re.sub(r"\s+", "", normalized)
    try:
        oku_match = re.search(r"([0-9]+(?:\.[0-9]+)?)億", normalized)
        man_match = re.search(r"([0-9]+(?:\.[0-9]+)?)万", normalized)
        if oku_match or man_match:
            amount = Decimal(0)
            if oku_match:
                amount += Decimal(oku_match.group(1)) * 100_000_000
            if man_match:
                amount += Decimal(man_match.group(1)) * 10_000
            return str(int(amount))

        unit_multipliers = (
            ("百万円", 1_000_000),
            ("千円", 1_000),
            ("万円", 10_000),
            ("円", 1),
        )
        for unit, multiplier in unit_multipliers:
            match = re.search(rf"([0-9]+(?:\.[0-9]+)?){unit}", normalized)
            if match:
                return str(int(Decimal(match.group(1)) * multiplier))
    except (InvalidOperation, ValueError):
        return ""
    return "".join(re.findall(r"[0-9]+", normalized))


def monetary_expressions(value: Any) -> list[str]:
    normalized = unicodedata.normalize("NFKC", str(value)).replace(",", "")
    normalized = re.sub(r"\s+", "", normalized)
    return re.findall(
        r"[0-9]+(?:\.[0-9]+)?億(?:[0-9]+(?:\.[0-9]+)?万円?)?"
        r"|[0-9]+(?:\.[0-9]+)?(?:百万円|千円|万円|円)",
        normalized,
    )


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
        normalized = unicodedata.normalize("NFKC", str(value))
        return "".join(re.findall(r"[0-9]+", normalized))
    if transform == "employment_insurance_office_number":
        normalized = unicodedata.normalize("NFKC", str(value))
        digits = "".join(re.findall(r"[0-9]+", normalized))
        return digits if len(digits) == 11 else ""
    if transform == "annual_sales_jpy":
        return annual_sales_jpy(value)
    if transform == "email_lower_trim":
        return unicodedata.normalize("NFKC", str(value)).strip().lower()
    if transform == "nationality_region":
        normalized = unicodedata.normalize("NFKC", str(value)).strip().lower()
        for aliases, rasens_value in NATIONALITY_REGION_VALUES:
            if normalized == rasens_value.lower() or normalized in aliases:
                return rasens_value
        return str(value).strip()
    if transform == "zero_to_empty":
        return "" if str(value).strip() in {"0", "0.0"} else str(value).strip()
    if transform == "kanji_only_text":
        text = str(value).strip()
        return text if re.search(r"[\u3400-\u9fff]", text) else ""
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


def clean_application_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(settings, dict):
        return {}

    cleaned: dict[str, Any] = {}
    intermediary_source = settings.get("intermediary")
    if isinstance(intermediary_source, dict):
        intermediary = {
            field: str(intermediary_source.get(field, "")).strip()
            for field in INTERMEDIARY_ENV_VARS
        }
        if all(intermediary.values()):
            cleaned["intermediary"] = intermediary

    receiving_source = settings.get("receiving_method")
    if isinstance(receiving_source, dict):
        notification_email = unicodedata.normalize(
            "NFKC", str(receiving_source.get("notification_email", ""))
        ).strip().lower()
        if notification_email:
            cleaned["receiving_method"] = {
                "method": "メール Email",
                "notification_email": notification_email,
                "notification_email_confirmation": notification_email,
            }

    return cleaned


def metadata_entry(field_metadata: Any, path: str) -> dict[str, Any]:
    if isinstance(field_metadata, dict):
        entry = field_metadata.get(path)
        return entry if isinstance(entry, dict) else {}
    if isinstance(field_metadata, list):
        for item in field_metadata:
            if not isinstance(item, dict):
                continue
            if item.get("field_path") == path or item.get("path") == path:
                return item
    return {}


def annual_sales_from_metadata(field_metadata: Any) -> str:
    meta = metadata_entry(field_metadata, "employer.annual_sales_jpy")
    if not meta or meta.get("human_edited") is True:
        return ""
    source_refs = meta.get("source_refs")
    if not isinstance(source_refs, list):
        return ""
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue
        quote = str(ref.get("text_quote", ""))
        expressions = monetary_expressions(quote)
        if len(expressions) != 1:
            continue
        value = annual_sales_jpy(expressions[0])
        if value:
            return value
    return ""


def apply_metadata_derived_values(source_data: dict[str, Any], field_metadata: Any) -> None:
    annual_sales = annual_sales_from_metadata(field_metadata)
    if annual_sales:
        ensure_dict(source_data, "employer")["annual_sales_jpy"] = annual_sales


def load_default_settings() -> dict[str, Any]:
    intermediary = {
        field: os.environ.get(env_name, "").strip()
        for field, env_name in INTERMEDIARY_ENV_VARS.items()
    }
    if not all(intermediary.values()):
        return {}

    return {"intermediary": intermediary}


def resolve_application_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings is None:
        return load_default_settings()
    return clean_application_settings(settings)


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
                "form_order": item.get("form_order", info["form_order"]),
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
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case_data = case_doc.get("case_data", {})
    settings = resolve_application_settings(settings)
    source_data = copy.deepcopy(case_data)
    source_data.pop("settings", None)
    if settings:
        source_data["settings"] = settings
    apply_application_defaults(source_data)
    apply_metadata_derived_values(source_data, case_doc.get("field_metadata"))
    workflow_state = case_doc.get("workflow_state") or case_data.get("case", {}).get("workflow_state", "")
    rows = build_rows(source_data, mapping, form_definitions)
    workflow_fillable = is_fillable_workflow_state(workflow_state)
    requires_intermediary = any(
        str(item.get("value_path", "")).startswith("settings.intermediary.")
        for item in mapping.get("mappings", [])
    )
    requires_receiving = any(
        str(item.get("value_path", "")).startswith("settings.receiving_method.")
        for item in mapping.get("mappings", [])
    )
    intermediary_configured = isinstance(settings.get("intermediary"), dict)
    receiving_configured = isinstance(settings.get("receiving_method"), dict)
    settings_configured = (
        (intermediary_configured or not requires_intermediary)
        and (receiving_configured or not requires_receiving)
    )
    fillable = workflow_fillable and settings_configured
    warnings = (
        []
        if workflow_fillable
        else [f"workflow_state is not fillable: {workflow_state or 'unknown'}"]
    )
    if requires_intermediary and not intermediary_configured:
        warnings.append("取次者の組織設定5件が揃っていないため、自動入力できません")
    if requires_receiving and not receiving_configured:
        warnings.append("通知送信用メールアドレスが組織設定にないため、自動入力できません")
    intermediary_gate = {
        "status": "verified" if intermediary_configured or not requires_intermediary else "blocked",
        "blocked_fields": [] if intermediary_configured or not requires_intermediary else list(INTERMEDIARY_PATHS),
    }
    settings_gate = {
        "status": "verified" if settings_configured else "blocked",
        "blocked_fields": (
            ([] if intermediary_configured or not requires_intermediary else list(INTERMEDIARY_PATHS))
            + ([] if receiving_configured or not requires_receiving else list(RECEIVING_PATHS))
        ),
    }

    return {
        "schema_version": "1.0",
        "case_id": case_doc.get("case_id") or case_data.get("case", {}).get("case_id", ""),
        "workflow_state": workflow_state,
        "fillable": fillable,
        "mapping_version": mapping.get("schema_version", ""),
        "form_definition": mapping.get("form_definition") or form_definitions.get("source_file", ""),
        "warnings": warnings,
        "intermediary_gate": intermediary_gate,
        "settings_gate": settings_gate,
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
    field_metadata: Any = None,
) -> dict[str, Any]:
    """Return case_data with deterministic display/fill defaults applied."""
    display_data = copy.deepcopy(case_data)
    display_data.pop("settings", None)
    display_settings = resolve_application_settings(settings)
    if display_settings:
        display_data["settings"] = copy.deepcopy(display_settings)
    apply_application_defaults(display_data)
    apply_metadata_derived_values(display_data, field_metadata)
    return display_data
