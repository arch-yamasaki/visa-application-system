"""Gemini response_schema contract tests."""

from extractors.schema import (
    BOOLEAN_VALUE_SCHEMA,
    EXTRACTION_SCHEMA,
    FIELD_VALUE_SCHEMA,
    SCOPE_SCHEMAS,
    SOURCE_REF_SCHEMA,
    _fv,
    to_response_json_schema,
)


def _value_type(field_schema: dict) -> str:
    return field_schema["properties"]["value"]["type"]


def test_default_field_value_is_string_and_source_ref_is_typed():
    assert FIELD_VALUE_SCHEMA["properties"]["value"]["type"] == "STRING"
    assert "alternatives" in FIELD_VALUE_SCHEMA["properties"]
    assert "alternatives" not in FIELD_VALUE_SCHEMA["required"]
    assert SOURCE_REF_SCHEMA["properties"]["page"]["type"] == "INTEGER"
    assert SOURCE_REF_SCHEMA["properties"]["confidence"]["type"] == "NUMBER"


def test_fv_propagates_value_type_to_alternatives():
    schema = _fv(BOOLEAN_VALUE_SCHEMA)

    assert schema["properties"]["value"]["type"] == "BOOLEAN"
    assert (
        schema["properties"]["alternatives"]["items"]["properties"]["value"]["type"]
        == "BOOLEAN"
    )


def test_identity_scope_uses_boolean_field_values():
    applicant = SCOPE_SCHEMAS["applicant_identity"]["properties"]["applicant"]["properties"]
    family = SCOPE_SCHEMAS["entry_plan"]["properties"]["applicant"]["properties"]["family"]["properties"]

    assert _value_type(applicant["name_roman"]) == "STRING"
    assert _value_type(family["has_accompanying_members"]) == "BOOLEAN"
    assert _value_type(family["has_japan_relatives_or_cohabitants"]) == "BOOLEAN"


def test_identity_scope_requires_passport_page_detection_metadata():
    identity = SCOPE_SCHEMAS["applicant_identity"]
    candidates = identity["properties"]["passport_identity_page_candidates"]
    item = candidates["items"]

    assert "passport_identity_page_candidates" in identity["required"]
    assert candidates["type"] == "ARRAY"
    assert item["properties"]["page"]["type"] == "INTEGER"
    assert item["properties"]["confidence"]["type"] == "NUMBER"
    assert item["properties"]["mrz_detected"]["type"] == "BOOLEAN"


def test_immigration_scope_uses_boolean_and_integer_field_values():
    immigration = (
        SCOPE_SCHEMAS["immigration_history"]["properties"]["applicant"]["properties"]
        ["immigration_history"]["properties"]
    )
    prior_coe = immigration["prior_coe_applications"]["properties"]

    assert _value_type(immigration["has_entries"]) == "BOOLEAN"
    assert _value_type(immigration["entries_count"]) == "INTEGER"
    assert _value_type(immigration["criminal_record"]) == "BOOLEAN"
    assert _value_type(immigration["deportation_or_departure_order"]) == "BOOLEAN"
    assert _value_type(immigration["deportation_count"]) == "INTEGER"
    assert _value_type(prior_coe["has_history"]) == "BOOLEAN"
    assert _value_type(prior_coe["count"]) == "INTEGER"
    assert _value_type(prior_coe["denial_count"]) == "INTEGER"


def test_employer_employment_and_education_scopes_use_minimal_typed_fields():
    employer = SCOPE_SCHEMAS["employer"]["properties"]["employer"]["properties"]
    employment = SCOPE_SCHEMAS["employment"]["properties"]["employment"]["properties"]
    education_applicant = SCOPE_SCHEMAS["education"]["properties"]["applicant"]["properties"]
    qualifications = education_applicant["qualifications"]["properties"]["it"]["properties"]
    history_item = (
        SCOPE_SCHEMAS["employment_history"]["properties"]["applicant"]["properties"]
        ["employment_history"]["items"]["properties"]
    )

    assert _value_type(employer["has_corporate_number"]) == "BOOLEAN"
    assert _value_type(employer["employee_count"]) == "STRING"
    assert _value_type(employment["has_position"]) == "BOOLEAN"
    assert _value_type(employment["monthly_salary"]) == "STRING"
    assert _value_type(qualifications["has_qualification"]) == "BOOLEAN"
    assert _value_type(history_item["start_month_unknown"]) == "BOOLEAN"
    assert _value_type(history_item["end_month_unknown"]) == "BOOLEAN"


def test_fallback_extraction_schema_has_same_typed_values():
    applicant = (
        EXTRACTION_SCHEMA["properties"]["case_data"]["properties"]["applicant"]["properties"]
    )
    immigration = applicant["immigration_history"]["properties"]
    employer = EXTRACTION_SCHEMA["properties"]["case_data"]["properties"]["employer"]["properties"]
    employment = EXTRACTION_SCHEMA["properties"]["case_data"]["properties"]["employment"]["properties"]

    assert _value_type(applicant["has_employment_history"]) == "BOOLEAN"
    assert _value_type(immigration["has_entries"]) == "BOOLEAN"
    assert _value_type(immigration["entries_count"]) == "INTEGER"
    assert _value_type(employer["has_corporate_number"]) == "BOOLEAN"
    assert _value_type(employment["has_position"]) == "BOOLEAN"


def test_review_schema_is_not_field_value_wrapped():
    review_schema = SCOPE_SCHEMAS["review"]
    assert review_schema["properties"]["missing_items"]["type"] == "ARRAY"
    assert "value" not in review_schema["properties"]["expected_route"]


def test_response_json_schema_uses_lowercase_types_and_defs():
    schema = to_response_json_schema(SCOPE_SCHEMAS["applicant_identity"])

    assert schema["type"] == "object"
    assert schema["properties"]["applicant"]["type"] == "object"
    assert schema["properties"]["applicant"]["properties"]["name_roman"] == {
        "$ref": "#/$defs/fieldValueString",
    }
    assert schema["$defs"]["fieldValueString"]["properties"]["source_ref"] == {
        "$ref": "#/$defs/sourceRef",
    }


def test_response_json_schema_keeps_locations_only_at_root():
    schema = to_response_json_schema(SCOPE_SCHEMAS["applicant_identity"])

    assert "source_locations" in schema["properties"]
    assert "source_locations" in schema["required"]
    assert schema["properties"]["source_locations"]["items"] == {
        "$ref": "#/$defs/sourceLocation",
    }
    assert "locations" not in schema["$defs"]["sourceRef"]["properties"]
    assert schema["$defs"]["sourceRef"]["required"] == [
        "document_id",
        "page",
        "text_quote",
        "confidence",
    ]


def test_response_json_schema_source_location_contract():
    schema = to_response_json_schema(SCOPE_SCHEMAS["applicant_identity"])
    location = schema["$defs"]["sourceLocation"]

    assert location["required"] == ["field_path", "alternative_index", "type"]
    assert location["properties"]["type"]["enum"] == [
        "pdf_bbox",
        "xlsx_cell",
        "docx_block",
    ]
    assert location["properties"]["bbox"] == {"$ref": "#/$defs/pdfBbox"}
    assert schema["$defs"]["pdfBbox"]["required"] == [
        "y_min",
        "x_min",
        "y_max",
        "x_max",
    ]


def test_response_json_schema_preserves_typed_field_values():
    schema = to_response_json_schema(SCOPE_SCHEMAS["entry_plan"])
    family = schema["properties"]["applicant"]["properties"]["family"]["properties"]

    assert family["has_accompanying_members"] == {
        "$ref": "#/$defs/fieldValueBoolean",
    }
    assert schema["$defs"]["fieldValueBoolean"]["properties"]["value"] == {
        "type": "boolean",
    }


def test_response_json_schema_review_does_not_add_source_locations():
    schema = to_response_json_schema(SCOPE_SCHEMAS["review"])

    assert schema["type"] == "object"
    assert "source_locations" not in schema["properties"]
    assert "$defs" not in schema
    assert schema["properties"]["expected_route"] == {
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ]
    }


def test_response_json_schema_does_not_mutate_canonical_schema():
    to_response_json_schema(SCOPE_SCHEMAS["applicant_identity"])

    source_ref = FIELD_VALUE_SCHEMA["properties"]["source_ref"]
    assert source_ref is SOURCE_REF_SCHEMA
    assert "locations" in SOURCE_REF_SCHEMA["properties"]
    assert "locations" in SOURCE_REF_SCHEMA["required"]
