"""Adapt display_case_data (Gemini extraction) to case_data.schema.json format."""

import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Month-name lookup (case-insensitive)
# ---------------------------------------------------------------------------

_MONTH_NAMES: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Patterns: "DD/MonthName/YYYY", "MonthName DD, YYYY", etc.
_RE_DMY_NAMED = re.compile(
    r"^(\d{1,2})[/\-\s]([A-Za-z]+)[/\-\s,]*(\d{4})$"
)
_RE_MDY_NAMED = re.compile(
    r"^([A-Za-z]+)[/\-\s]+(\d{1,2})[/\-\s,]+(\d{4})$"
)


def _normalize_date(value: str) -> str:
    """Normalize various date formats to YYYY-MM-DD.

    Handles:
      - Already ISO: "2024-12-28" -> "2024-12-28"
      - DD/MonthName/YYYY: "28/December/2024" -> "2024-12-28"
      - MonthName DD, YYYY: "December 28, 2024" -> "2024-12-28"
      - DD/MM/YYYY: "28/12/2024" -> "2024-12-28"
    Returns the original string if no pattern matches.
    """
    s = value.strip()
    if not s:
        return s

    # Already YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s

    # DD/MonthName/YYYY  (e.g. "28/December/2024")
    m = _RE_DMY_NAMED.match(s)
    if m:
        day, month_name, year = m.group(1), m.group(2), m.group(3)
        mm = _MONTH_NAMES.get(month_name.lower())
        if mm:
            return f"{year}-{mm}-{day.zfill(2)}"

    # MonthName DD, YYYY  (e.g. "December 28, 2024")
    m = _RE_MDY_NAMED.match(s)
    if m:
        month_name, day, year = m.group(1), m.group(2), m.group(3)
        mm = _MONTH_NAMES.get(month_name.lower())
        if mm:
            return f"{year}-{mm}-{day.zfill(2)}"

    # DD/MM/YYYY  (e.g. "28/12/2024")
    m = re.fullmatch(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", s)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    return s


# Dot-paths of date fields in the *output* (post-adapt) structure.
_DATE_FIELD_PATHS: list[str] = [
    "applicant.birth_date",
    "passport.expiry_date",
    "application.planned_entry_date",
    "immigration_history.latest_entry.start_date",
    "immigration_history.latest_entry.end_date",
    "education.0.graduation_date",
    "contract.start_date",
]

# ---------------------------------------------------------------------------
# Rename mapping: visa-app flat key -> autofill key
# ---------------------------------------------------------------------------

_RENAMES: dict[str, str] = {
    "applicant.nationality": "applicant.nationality_region",
    "applicant.date_of_birth": "applicant.birth_date",
    "applicant.gender": "applicant.sex",
    "applicant.place_of_birth": "applicant.birth_place",
    "employer.employment_insurance_no": "employer.employment_insurance_office_number",
    "employer.company_name": "employer.name",
    "employer.capital": "employer.capital_jpy",
    "employer.sales": "employer.annual_sales_jpy",
    "employer.employees": "employer.employee_count",
    "immigration_history.has_criminal_record": "immigration_history.criminal_record",
}

# ---------------------------------------------------------------------------
# Nest mapping: visa-app flat key -> autofill nested key
# ---------------------------------------------------------------------------

_NESTS: dict[str, str] = {
    "applicant.japan_postal_code": "applicant.japan_contact.postal_code",
    "applicant.japan_address": "applicant.japan_contact.address",
    "applicant.japan_phone": "applicant.japan_contact.phone",
    "applicant.japan_mobile": "applicant.japan_contact.mobile",
    "applicant.email": "applicant.japan_contact.email",
    "immigration_history.latest_entry_start": "immigration_history.latest_entry.start_date",
    "immigration_history.latest_entry_end": "immigration_history.latest_entry.end_date",
    "immigration_history.has_deportation": "immigration_history.deportation_or_departure_order",
}

# ---------------------------------------------------------------------------
# Structural moves: visa-app key -> autofill key (different section)
# ---------------------------------------------------------------------------

_MOVES: dict[str, str] = {
    "immigration_history.has_prior_coe": "immigration_history.prior_coe_applications.has_history",
    "immigration_history.prior_coe_count": "immigration_history.prior_coe_applications.count",
    "immigration_history.prior_coe_denial_count": "immigration_history.prior_coe_applications.denial_count",
    "application.has_accompanying": "family.has_accompanying_members",
    "activity_details.description": "application.activity_details",
}

# ---------------------------------------------------------------------------
# Defaults for fields that always have fixed values in tech-humanities-intl
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, str] = {
    "application.desired_status_label": "技術・人文知識・国際業務",
    "case.application_type": "certificate_of_eligibility",
    "case.target_status": "engineer_humanities_international",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(data: dict, dotpath: str):
    """Get a value from a nested dict by dot-separated path."""
    current = data
    for key in dotpath.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _set(data: dict, dotpath: str, value) -> None:
    """Set a value in a nested dict by dot-separated path, creating intermediates."""
    keys = dotpath.split(".")
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _apply_mappings(src: dict, out: dict, mapping: dict[str, str]) -> None:
    """For each src_path -> dst_path in mapping, copy value from src to out."""
    for src_path, dst_path in mapping.items():
        val = _get(src, src_path)
        if val is not None:
            _set(out, dst_path, val)


def _copy_section(src: dict, out: dict, section: str) -> None:
    """Copy a top-level section as-is if it exists."""
    val = src.get(section)
    if val is not None:
        out[section] = val


def _normalize_date_fields(data: dict) -> None:
    """Normalize all known date fields in data to YYYY-MM-DD in-place."""
    for dotpath in _DATE_FIELD_PATHS:
        # Handle array paths like "education.0.graduation_date"
        parts = dotpath.split(".")
        current = data
        for part in parts[:-1]:
            if current is None:
                break
            if isinstance(current, list):
                idx = int(part) if part.isdigit() else -1
                current = current[idx] if 0 <= idx < len(current) else None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
        if not isinstance(current, dict):
            continue
        field = parts[-1]
        val = current.get(field)
        if isinstance(val, str) and val:
            normalized = _normalize_date(val)
            if normalized != val:
                current[field] = normalized


def _build_education_array(src: dict) -> list[dict] | None:
    """Convert S3 education (single object) to autofill education (array).

    S3 produces: education.{level, level_detail, school_name, graduation_date, ...}
                 major.{field, field_other}
    Autofill expects: education = [{level, school_name, major, graduation_date, ...}]
    """
    edu = src.get("education")
    if not isinstance(edu, dict):
        return None

    entry = dict(edu)  # shallow copy
    # Merge major fields into education entry
    major = src.get("major")
    if isinstance(major, dict):
        entry["major"] = major.get("field") or major.get("field_other")

    return [entry]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def adapt(display_case_data: dict, case_doc: dict) -> dict:
    """Convert display_case_data to case_data.schema.json format.

    Args:
        display_case_data: Flat value dict from Gemini extraction.
        case_doc: Firestore case document (for case_id, workflow_state, etc.).

    Returns:
        Dict conforming to case_data.schema.json.
    """
    src = display_case_data
    out: dict = {"schema_version": "1.0"}

    # --- case section (from Firestore doc + defaults) ---
    out["case"] = {
        "case_id": case_doc.get("case_id", ""),
        "application_type": _DEFAULTS["case.application_type"],
        "target_status": _DEFAULTS["case.target_status"],
        "workflow_state": case_doc.get("workflow_state", "draft"),
    }

    # --- Sections that pass through unchanged ---
    _copy_section(src, out, "passport")
    _copy_section(src, out, "contract")
    _copy_section(src, out, "employment_conditions")
    _copy_section(src, out, "it_qualification")

    # --- Sections with field renames ---
    _apply_mappings(src, out, _RENAMES)

    # --- Sections with flat -> nested conversion ---
    _apply_mappings(src, out, _NESTS)

    # --- Structural moves ---
    _apply_mappings(src, out, _MOVES)

    # --- Fields that copy straight through (applicant, employer, etc.) ---
    # Copy remaining applicant fields not handled by renames/nests
    for key in ("name_roman", "marital_status", "occupation", "home_country_address"):
        val = _get(src, f"applicant.{key}")
        if val is not None:
            _set(out, f"applicant.{key}", val)

    # Copy remaining employer fields not handled by renames
    _EMPLOYER_RENAMED = {"employment_insurance_no", "company_name", "capital", "sales", "employees"}
    employer = src.get("employer")
    if isinstance(employer, dict):
        out_employer = out.setdefault("employer", {})
        for key, val in employer.items():
            if key in _EMPLOYER_RENAMED:
                continue  # already renamed via _RENAMES
            if key not in out_employer:
                out_employer[key] = val

    # Copy remaining immigration_history fields not handled by renames/nests/moves
    for key in ("has_entries", "entries_count", "deportation_count", "deportation_latest"):
        val = _get(src, f"immigration_history.{key}")
        if val is not None:
            _set(out, f"immigration_history.{key}", val)

    # Copy remaining application fields not handled by moves
    for key in ("purpose_of_entry", "planned_entry_date", "planned_port",
                "planned_period_years", "planned_period_months",
                "visa_application_location"):
        val = _get(src, f"application.{key}")
        if val is not None:
            _set(out, f"application.{key}", val)

    # --- Default: desired_status_label ---
    out.setdefault("application", {}).setdefault(
        "desired_status_label", _DEFAULTS["application.desired_status_label"],
    )

    # --- Education: single object -> array ---
    edu_array = _build_education_array(src)
    if edu_array is not None:
        out["education"] = edu_array

    # --- Normalize date fields to YYYY-MM-DD ---
    _normalize_date_fields(out)

    return out
