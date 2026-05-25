"""Gemini API response_schema for structured extraction.

Defines EXTRACTION_SCHEMA — a JSON Schema dict using Gemini's type
conventions (uppercase type names: STRING, OBJECT, ARRAY, INTEGER, NUMBER,
BOOLEAN).

Design: every data field is wrapped in FieldValue = {value, source} where
source is a compact string encoding "document_id|page|text_quote|confidence".
This keeps the schema small enough to avoid Gemini's "too many states" error.

The original design used {value, source_refs: [{document_id, page,
text_quote, confidence}]} but that produced too many schema constraints.
Downstream code in gemini.py parses the source string back into structured
source_refs.

The top-level review section keeps its own shape (not FieldValue-wrapped).
"""

# ---------------------------------------------------------------------------
# FieldValue — the common wrapper for every extracted field
# ---------------------------------------------------------------------------

FIELD_VALUE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "value": {"type": "STRING"},
        "source": {"type": "STRING"},
    },
    "required": ["value", "source"],
}


def _fv() -> dict:
    """Return a fresh copy of FIELD_VALUE_SCHEMA (avoids shared-mutation)."""
    import copy
    return copy.deepcopy(FIELD_VALUE_SCHEMA)


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _object_of_fields(field_names: list[str]) -> dict:
    """Build an OBJECT schema where every property is a FieldValue."""
    return {
        "type": "OBJECT",
        "properties": {name: _fv() for name in field_names},
        "required": field_names,
    }


# ---------------------------------------------------------------------------
# Review section — NOT wrapped in FieldValue
# ---------------------------------------------------------------------------

_REVIEW_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "expected_route": {"type": "STRING", "nullable": True},
        "missing_items": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "findings": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "validation_errors": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": ["expected_route", "missing_items", "findings", "validation_errors"],
}

# ===========================================================================
# Scoped schemas — Phase 1 (S1, S2, S3, S6)
# ===========================================================================

# ---------------------------------------------------------------------------
# SCOPE1: Identity (身分事項, RASENS No.1〜20)
# ---------------------------------------------------------------------------

_S1_APPLICANT_BASE = _object_of_fields([
    "nationality_region",
    "birth_date",
    "name_roman",
    "sex",
    "birth_place",
    "marital_status",
    "occupation",
    "home_country_address",
])

_S1_PASSPORT = _object_of_fields([
    "number",
    "expiry_date",
])

_S1_JAPAN_CONTACT = _object_of_fields([
    "postal_code",
    "address",
    "phone",
    "mobile",
    "email",
])

_S1_FAMILY = _object_of_fields([
    "has_accompanying_members",
    "has_japan_relatives_or_cohabitants",
])

_S1_ENTRY_PLAN = _object_of_fields([
    "purpose_of_entry",
    "planned_entry_date",
    "planned_port",
    "planned_period_years",
    "planned_period_months",
    "visa_application_location",
])

_S1_IMMIGRATION_HISTORY = _object_of_fields([
    "has_entries",
    "entries_count",
    "criminal_record",
    "deportation_or_departure_order",
    "deportation_count",
    "deportation_latest",
])

_S1_LATEST_ENTRY = _object_of_fields([
    "start_date",
    "end_date",
])

_S1_PRIOR_COE = _object_of_fields([
    "has_history",
    "count",
    "denial_count",
])

_S1_IMMIGRATION_HISTORY["properties"]["latest_entry"] = _S1_LATEST_ENTRY
_S1_IMMIGRATION_HISTORY["properties"]["prior_coe_applications"] = _S1_PRIOR_COE
_S1_IMMIGRATION_HISTORY["required"].extend(["latest_entry", "prior_coe_applications"])

_S1_APPLICANT = _S1_APPLICANT_BASE
_S1_APPLICANT["properties"]["japan_contact"] = _S1_JAPAN_CONTACT
_S1_APPLICANT["properties"]["passport"] = _S1_PASSPORT
_S1_APPLICANT["properties"]["immigration_history"] = _S1_IMMIGRATION_HISTORY
_S1_APPLICANT["properties"]["family"] = _S1_FAMILY
_S1_APPLICANT["required"].extend(["japan_contact", "passport", "immigration_history", "family"])

SCOPE1_IDENTITY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "applicant": _S1_APPLICANT,
        "entry_plan": _S1_ENTRY_PLAN,
    },
    "required": ["applicant", "entry_plan"],
}

# ---------------------------------------------------------------------------
# SCOPE2: Employer + Employment conditions + Activity (所属機関+雇用条件+活動内容, No.2〜11)
# ---------------------------------------------------------------------------

_S2_EMPLOYMENT = _object_of_fields([
    "contract_type",
    "employment_period_type",
    "employment_period_years",
    "employment_period_months",
    "joining_date",
    "monthly_salary",
    "experience_months",
    "has_position",
    "position_title",
    "job_category_primary",
    "activity_details",
])

_S2_EMPLOYER = _object_of_fields([
    "name",
    "has_corporate_number",
    "corporate_number",
    "office_name",
    "employment_insurance_office_number",
    "industry_primary",
    "industry_other",
    "postal_code",
    "address",
    "phone",
    "capital_jpy",
    "annual_sales_jpy",
    "employee_count",
    "foreign_employee_count",
    "technical_intern_count",
])

SCOPE2_EMPLOYER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "employer": _S2_EMPLOYER,
        "employment": _S2_EMPLOYMENT,
    },
    "required": ["employer", "employment"],
}

# ---------------------------------------------------------------------------
# SCOPE3: Education + Qualification (学歴+資格, No.23〜25)
# ---------------------------------------------------------------------------

_S3_EDUCATION = _object_of_fields([
    "level",
    "level_detail",
    "level_other",
    "school_name",
    "major_field",
    "major_field_other",
    "graduation_date",
])

_S3_IT_QUALIFICATION = _object_of_fields([
    "has_qualification",
    "qualification_name",
])

_S3_QUALIFICATIONS = {
    "type": "OBJECT",
    "properties": {
        "it": _S3_IT_QUALIFICATION,
    },
    "required": ["it"],
}

_S3_APPLICANT = {
    "type": "OBJECT",
    "properties": {
        "education": {
            "type": "ARRAY",
            "items": _S3_EDUCATION,
        },
        "qualifications": _S3_QUALIFICATIONS,
    },
    "required": ["education", "qualifications"],
}

SCOPE3_EDUCATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "applicant": _S3_APPLICANT,
    },
    "required": ["applicant"],
}

# ---------------------------------------------------------------------------
# SCOPE6: Review (レビュー — NOT FieldValue-wrapped)
# ---------------------------------------------------------------------------

SCOPE6_REVIEW_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "expected_route": {"type": "STRING", "nullable": True},
        "missing_items": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "findings": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "validation_errors": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": ["expected_route", "missing_items", "findings", "validation_errors"],
}

# ---------------------------------------------------------------------------
# Registry: all scoped schemas
# ---------------------------------------------------------------------------

SCOPE_SCHEMAS: dict[str, dict] = {
    "S1": SCOPE1_IDENTITY_SCHEMA,
    "S2": SCOPE2_EMPLOYER_SCHEMA,
    "S3": SCOPE3_EDUCATION_SCHEMA,
    "S6": SCOPE6_REVIEW_SCHEMA,
}


def _combined_applicant_schema() -> dict:
    """Build the non-scoped fallback applicant schema from scoped pieces."""
    import copy

    applicant = copy.deepcopy(_S1_APPLICANT)
    applicant["properties"]["education"] = {
        "type": "ARRAY",
        "items": _S3_EDUCATION,
    }
    applicant["properties"]["qualifications"] = _S3_QUALIFICATIONS
    applicant["required"].extend(["education", "qualifications"])
    return applicant


EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "case_data": {
            "type": "OBJECT",
            "properties": {
                "applicant": _combined_applicant_schema(),
                "entry_plan": _S1_ENTRY_PLAN,
                "employer": _S2_EMPLOYER,
                "employment": _S2_EMPLOYMENT,
            },
            "required": ["applicant", "entry_plan", "employer", "employment"],
        },
        "review": _REVIEW_SCHEMA,
    },
    "required": ["case_data", "review"],
}
