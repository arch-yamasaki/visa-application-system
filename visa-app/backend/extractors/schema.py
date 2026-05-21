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
# Sections
# ---------------------------------------------------------------------------

_APPLICANT_SCHEMA = _object_of_fields([
    "name_roman",
    "nationality",
    "date_of_birth",
    "gender",
    "passport_number",
    "passport_expiration",
    "place_of_birth",
    "hometown",
    "marital_status",
    "occupation",
])

_EMPLOYMENT_CONDITIONS_SCHEMA = _object_of_fields([
    "company_name",
    "job_title",
    "duties",
    "monthly_salary",
    "annual_salary",
    "bonus",
    "working_hours",
    "holidays",
    "insurance",
    "joining_date",
    "contract_type",
    "contract_period",
    "contract_start_date",
    "contract_end_date",
    "work_location",
    "allowances",
])

# education is an ARRAY of objects
_EDUCATION_ITEM_SCHEMA = _object_of_fields([
    "school_name",
    "major",
    "graduation_date",
])

_EDUCATION_SCHEMA = {
    "type": "ARRAY",
    "items": _EDUCATION_ITEM_SCHEMA,
}

_EMPLOYER_SCHEMA = _object_of_fields([
    "company_name",
    "address",
    "capital",
    "employees",
    "corporate_number",
    "representative_name",
    "business_category",
    "sales",
])

_ENTRY_HISTORY_SCHEMA = _object_of_fields([
    "past_entry",
    "past_coe",
    "past_entry_count",
    "past_coe_count",
    "latest_entry",
    "departure_order",
])

_CRIMINAL_RECORD_SCHEMA = _object_of_fields([
    "has_record",
])

_FAMILY_IN_JAPAN_SCHEMA = _object_of_fields([
    "members",
])

_ACTIVITY_DETAILS_SCHEMA = _object_of_fields([
    "description",
])

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

# ---------------------------------------------------------------------------
# Top-level extraction schema (legacy — kept for backward compatibility)
# ---------------------------------------------------------------------------

EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "case_data": {
            "type": "OBJECT",
            "properties": {
                "applicant": _APPLICANT_SCHEMA,
                "employment_conditions": _EMPLOYMENT_CONDITIONS_SCHEMA,
                "education": _EDUCATION_SCHEMA,
                "employer": _EMPLOYER_SCHEMA,
                "entry_history": _ENTRY_HISTORY_SCHEMA,
                "criminal_record": _CRIMINAL_RECORD_SCHEMA,
                "family_in_japan": _FAMILY_IN_JAPAN_SCHEMA,
                "activity_details": _ACTIVITY_DETAILS_SCHEMA,
            },
            "required": [
                "applicant",
                "employment_conditions",
                "education",
                "employer",
                "entry_history",
                "criminal_record",
                "family_in_japan",
                "activity_details",
            ],
        },
        "review": _REVIEW_SCHEMA,
    },
    "required": ["case_data", "review"],
}


# ===========================================================================
# Scoped schemas — Phase 1 (S1, S2, S3, S6)
# ===========================================================================

# ---------------------------------------------------------------------------
# SCOPE1: Identity (身分事項, RASENS No.1〜20)
# ---------------------------------------------------------------------------

_S1_APPLICANT = _object_of_fields([
    "nationality",
    "date_of_birth",
    "name_roman",
    "gender",
    "place_of_birth",
    "marital_status",
    "occupation",
    "home_country_address",
    "japan_postal_code",
    "japan_address",
    "japan_phone",
    "japan_mobile",
    "email",
])

_S1_PASSPORT = _object_of_fields([
    "number",
    "expiry_date",
])

_S1_APPLICATION = _object_of_fields([
    "purpose_of_entry",
    "planned_entry_date",
    "planned_port",
    "planned_period_years",
    "planned_period_months",
    "has_accompanying",
    "visa_application_location",
])

_S1_IMMIGRATION_HISTORY = _object_of_fields([
    "has_entries",
    "entries_count",
    "latest_entry_start",
    "latest_entry_end",
    "has_prior_coe",
    "prior_coe_count",
    "prior_coe_denial_count",
    "has_criminal_record",
    "has_deportation",
    "deportation_count",
    "deportation_latest",
])

SCOPE1_IDENTITY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "applicant": _S1_APPLICANT,
        "passport": _S1_PASSPORT,
        "application": _S1_APPLICATION,
        "immigration_history": _S1_IMMIGRATION_HISTORY,
    },
    "required": ["applicant", "passport", "application", "immigration_history"],
}

# ---------------------------------------------------------------------------
# SCOPE2: Employer + Employment conditions + Activity (所属機関+雇用条件+活動内容, No.2〜11)
# ---------------------------------------------------------------------------

_S2_CONTRACT = _object_of_fields([
    "contract_type",
])

_S2_EMPLOYER = _object_of_fields([
    "name",
    "has_corporate_number",
    "corporate_number",
    "office_name",
    "employment_insurance_no",
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

_S2_EMPLOYMENT_CONDITIONS = _object_of_fields([
    "employment_period_type",
    "employment_period_years",
    "employment_period_months",
    "joining_date",
    "monthly_salary",
    "experience_months",
    "has_position",
    "position_title",
    "job_category_primary",
])

_S2_ACTIVITY_DETAILS = _object_of_fields([
    "description",
])

SCOPE2_EMPLOYER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "contract": _S2_CONTRACT,
        "employer": _S2_EMPLOYER,
        "employment_conditions": _S2_EMPLOYMENT_CONDITIONS,
        "activity_details": _S2_ACTIVITY_DETAILS,
    },
    "required": ["contract", "employer", "employment_conditions", "activity_details"],
}

# ---------------------------------------------------------------------------
# SCOPE3: Education + Qualification (学歴+資格, No.23〜25)
# ---------------------------------------------------------------------------

_S3_EDUCATION = _object_of_fields([
    "level",
    "level_detail",
    "level_other",
    "school_name",
    "graduation_date",
])

_S3_MAJOR = _object_of_fields([
    "field",
    "field_other",
])

_S3_IT_QUALIFICATION = _object_of_fields([
    "has_qualification",
    "qualification_name",
])

SCOPE3_EDUCATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "education": _S3_EDUCATION,
        "major": _S3_MAJOR,
        "it_qualification": _S3_IT_QUALIFICATION,
    },
    "required": ["education", "major", "it_qualification"],
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
