"""Source location schema contract tests."""

from extractors.schema import (
    FIELD_VALUE_SCHEMA,
    SCOPE_SCHEMAS,
    SOURCE_REF_SCHEMA,
    to_response_json_schema,
)


def test_field_value_requires_value_and_source_ref():
    assert FIELD_VALUE_SCHEMA["required"] == ["value", "source_ref"]
    assert "origin" not in FIELD_VALUE_SCHEMA["properties"]
    alternative = FIELD_VALUE_SCHEMA["properties"]["alternatives"]["items"]
    assert alternative["required"] == ["value", "source_ref"]
    assert "origin" not in alternative["properties"]


def test_source_ref_requires_locations():
    assert SOURCE_REF_SCHEMA["required"] == [
        "document_id",
        "page",
        "text_quote",
        "confidence",
        "locations",
    ]

    location_schema = SOURCE_REF_SCHEMA["properties"]["locations"]["items"]
    assert location_schema["properties"]["type"]["enum"] == [
        "pdf_bbox",
        "xlsx_cell",
        "docx_block",
    ]


def test_pdf_bbox_requires_all_coordinates():
    location_schema = SOURCE_REF_SCHEMA["properties"]["locations"]["items"]
    bbox_schema = location_schema["properties"]["bbox"]

    assert bbox_schema["required"] == ["y_min", "x_min", "y_max", "x_max"]


def test_response_json_schema_has_root_source_locations_once():
    schema = to_response_json_schema(SCOPE_SCHEMAS["employment"])

    assert schema["properties"]["source_locations"] == {
        "type": "array",
        "items": {"$ref": "#/$defs/sourceLocation"},
    }
    assert "locations" not in schema["$defs"]["sourceRef"]["properties"]
