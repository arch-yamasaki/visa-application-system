"""Gemini API response_schema for structured extraction.

Defines EXTRACTION_SCHEMA — a JSON Schema dict using Gemini's type
conventions (uppercase type names: STRING, OBJECT, ARRAY, INTEGER, NUMBER,
BOOLEAN).

Design: every data field is wrapped in FieldValue = {value, source_ref}.
source_ref is a single primary evidence object. Downstream code in gemini.py
normalizes source_ref into field_metadata.source_refs[] for UI compatibility.

The top-level review section keeps its own shape (not FieldValue-wrapped).
"""

# ---------------------------------------------------------------------------
# FieldValue — the common wrapper for every extracted field
# ---------------------------------------------------------------------------

SOURCE_REF_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "document_id": {"type": "STRING"},
        "page": {"type": "INTEGER"},
        "text_quote": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["document_id", "page", "text_quote", "confidence"],
}

STRING_VALUE_SCHEMA = {"type": "STRING"}
BOOLEAN_VALUE_SCHEMA = {"type": "BOOLEAN"}
INTEGER_VALUE_SCHEMA = {"type": "INTEGER"}

FIELD_VALUE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "value": STRING_VALUE_SCHEMA,
        "source_ref": SOURCE_REF_SCHEMA,
    },
    "required": ["value", "source_ref"],
}


def _fv(value_schema: dict | None = None) -> dict:
    """Return a fresh FieldValue schema with the requested value type."""
    import copy

    schema = copy.deepcopy(FIELD_VALUE_SCHEMA)
    schema["properties"]["value"] = copy.deepcopy(value_schema or STRING_VALUE_SCHEMA)
    return schema


def _bool_fv() -> dict:
    return _fv(BOOLEAN_VALUE_SCHEMA)


def _int_fv() -> dict:
    return _fv(INTEGER_VALUE_SCHEMA)


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _object_of_fields(field_names: list[str], field_types: dict[str, dict] | None = None) -> dict:
    """Build an OBJECT schema where every property is a FieldValue."""
    field_types = field_types or {}
    return {
        "type": "OBJECT",
        "properties": {name: _fv(field_types.get(name)) for name in field_names},
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

_S1_FAMILY = _object_of_fields(
    [
        "has_accompanying_members",
        "has_japan_relatives_or_cohabitants",
    ],
    {
        "has_accompanying_members": BOOLEAN_VALUE_SCHEMA,
        "has_japan_relatives_or_cohabitants": BOOLEAN_VALUE_SCHEMA,
    },
)

_S1_JAPAN_RELATIVE = _object_of_fields(
    [
        "relationship",
        "name",
        "birth_date",
        "nationality_region",
        "will_cohabit",
        "workplace_or_school_name",
        "residence_card_or_certificate_number",
    ],
    {"will_cohabit": BOOLEAN_VALUE_SCHEMA},
)

_S1_FAMILY["properties"]["japan_relatives_or_cohabitants"] = {
    "type": "ARRAY",
    "items": _S1_JAPAN_RELATIVE,
}
_S1_FAMILY["required"].append("japan_relatives_or_cohabitants")

_S1_ENTRY_PLAN = _object_of_fields([
    "main_activity_category",
    "purpose_of_entry",
    "planned_entry_date",
    "planned_port",
    "planned_period_years",
    "planned_period_months",
    "visa_application_location",
])

_S1_IMMIGRATION_HISTORY = _object_of_fields(
    [
        "has_entries",
        "entries_count",
        "criminal_record",
        "deportation_or_departure_order",
        "deportation_count",
        "deportation_latest",
    ],
    {
        "has_entries": BOOLEAN_VALUE_SCHEMA,
        "entries_count": INTEGER_VALUE_SCHEMA,
        "criminal_record": BOOLEAN_VALUE_SCHEMA,
        "deportation_or_departure_order": BOOLEAN_VALUE_SCHEMA,
        "deportation_count": INTEGER_VALUE_SCHEMA,
    },
)

_S1_LATEST_ENTRY = _object_of_fields([
    "start_date",
    "end_date",
])

_S1_PRIOR_COE = _object_of_fields(
    [
        "has_history",
        "count",
        "denial_count",
    ],
    {
        "has_history": BOOLEAN_VALUE_SCHEMA,
        "count": INTEGER_VALUE_SCHEMA,
        "denial_count": INTEGER_VALUE_SCHEMA,
    },
)

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

_S2_EMPLOYMENT = _object_of_fields(
    [
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
    ],
    {"has_position": BOOLEAN_VALUE_SCHEMA},
)

_S2_EMPLOYER = _object_of_fields(
    [
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
    ],
    {"has_corporate_number": BOOLEAN_VALUE_SCHEMA},
)

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
    "country_type",
    "level",
    "level_detail",
    "level_other",
    "school_name",
    "major_field",
    "major_field_other",
    "graduation_date",
])

_S3_IT_QUALIFICATION = _object_of_fields(
    [
        "has_qualification",
        "qualification_name",
    ],
    {"has_qualification": BOOLEAN_VALUE_SCHEMA},
)

_S3_EMPLOYMENT_HISTORY = _object_of_fields(
    [
        "country_region",
        "start_month_unknown",
        "start_date",
        "end_month_unknown",
        "end_date",
        "company_name_en",
        "company_name_local",
    ],
    {
        "start_month_unknown": BOOLEAN_VALUE_SCHEMA,
        "end_month_unknown": BOOLEAN_VALUE_SCHEMA,
    },
)

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
        "has_employment_history": _bool_fv(),
        "employment_history": {
            "type": "ARRAY",
            "items": _S3_EMPLOYMENT_HISTORY,
        },
        "education": {
            "type": "ARRAY",
            "items": _S3_EDUCATION,
        },
        "qualifications": _S3_QUALIFICATIONS,
    },
    "required": ["has_employment_history", "employment_history", "education", "qualifications"],
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

SCOPE_APPLICANT_IDENTITY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "applicant": {
            "type": "OBJECT",
            "properties": {
                "nationality_region": _fv(),
                "birth_date": _fv(),
                "name_roman": _fv(),
                "sex": _fv(),
                "birth_place": _fv(),
                "marital_status": _fv(),
                "occupation": _fv(),
                "home_country_address": _fv(),
                "japan_contact": _S1_JAPAN_CONTACT,
                "passport": _S1_PASSPORT,
            },
            "required": [
                "nationality_region",
                "birth_date",
                "name_roman",
                "sex",
                "birth_place",
                "marital_status",
                "occupation",
                "home_country_address",
                "japan_contact",
                "passport",
            ],
        },
    },
    "required": ["applicant"],
}

SCOPE_ENTRY_PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "entry_plan": _S1_ENTRY_PLAN,
        "applicant": {
            "type": "OBJECT",
            "properties": {
                "family": _S1_FAMILY,
            },
            "required": ["family"],
        },
    },
    "required": ["entry_plan", "applicant"],
}

SCOPE_IMMIGRATION_HISTORY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "applicant": {
            "type": "OBJECT",
            "properties": {
                "immigration_history": _S1_IMMIGRATION_HISTORY,
            },
            "required": ["immigration_history"],
        },
    },
    "required": ["applicant"],
}

SCOPE_EDUCATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "applicant": {
            "type": "OBJECT",
            "properties": {
                "education": {
                    "type": "ARRAY",
                    "items": _S3_EDUCATION,
                },
                "qualifications": _S3_QUALIFICATIONS,
            },
            "required": ["education", "qualifications"],
        },
    },
    "required": ["applicant"],
}

SCOPE_EMPLOYMENT_HISTORY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "applicant": {
            "type": "OBJECT",
            "properties": {
                "has_employment_history": _bool_fv(),
                "employment_history": {
                    "type": "ARRAY",
                    "items": _S3_EMPLOYMENT_HISTORY,
                },
            },
            "required": ["has_employment_history", "employment_history"],
        },
    },
    "required": ["applicant"],
}

SCOPE_EMPLOYER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "employer": _S2_EMPLOYER,
    },
    "required": ["employer"],
}

SCOPE_EMPLOYMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "employment": _S2_EMPLOYMENT,
    },
    "required": ["employment"],
}

SCOPE_SCHEMAS: dict[str, dict] = {
    "applicant_identity": SCOPE_APPLICANT_IDENTITY_SCHEMA,
    "entry_plan": SCOPE_ENTRY_PLAN_SCHEMA,
    "immigration_history": SCOPE_IMMIGRATION_HISTORY_SCHEMA,
    "education": SCOPE_EDUCATION_SCHEMA,
    "employment_history": SCOPE_EMPLOYMENT_HISTORY_SCHEMA,
    "employer": SCOPE_EMPLOYER_SCHEMA,
    "employment": SCOPE_EMPLOYMENT_SCHEMA,
    "review": SCOPE6_REVIEW_SCHEMA,
    # Legacy aliases kept while scoped extraction tests and docs migrate.
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
    applicant["properties"]["has_employment_history"] = _bool_fv()
    applicant["properties"]["employment_history"] = {
        "type": "ARRAY",
        "items": _S3_EMPLOYMENT_HISTORY,
    }
    applicant["properties"]["qualifications"] = _S3_QUALIFICATIONS
    applicant["required"].extend(["has_employment_history", "employment_history", "education", "qualifications"])
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
