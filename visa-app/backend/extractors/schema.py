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
# Top-level extraction schema
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
