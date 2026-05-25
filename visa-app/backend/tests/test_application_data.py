"""application_data generator tests."""

import pytest

from application_data import build_application_data, build_rows, is_fillable_workflow_state


FORM_DEFINITIONS = {
    "source_file": "rasens_offer_fields.json",
    "fields": [
        {
            "section": "申請概要",
            "no": "",
            "label": "主たる活動内容",
            "required": True,
            "controls": [
                {
                    "field_id": "select_256097",
                    "field_name": "item[1].selectData",
                    "input_type": "select",
                }
            ],
        },
        {
            "section": "身分事項",
            "no": "2",
            "label": "生年月日",
            "required": True,
            "controls": [
                {
                    "field_id": "textData1_256102",
                    "field_name": "",
                    "input_type": "text",
                }
            ],
        },
        {
            "section": "身分事項",
            "no": "17.2",
            "label": "過去の出入国歴 回数",
            "required": False,
            "controls": [
                {
                    "field_id": "select_256126",
                    "field_name": "item[30].selectData",
                    "input_type": "select",
                }
            ],
        },
        {
            "section": "所属機関に関する情報等",
            "no": "11",
            "label": "活動内容詳細",
            "required": True,
            "controls": [
                {
                    "field_id": "switch_256306",
                    "field_name": "item[210].textData",
                    "input_type": "textarea",
                }
            ],
        },
        {
            "section": "取次者",
            "no": "",
            "label": "取次者 氏名",
            "required": True,
            "controls": [
                {
                    "field_id": "switch_256263",
                    "field_name": "item[167].textData",
                    "input_type": "text",
                }
            ],
        },
    ],
}


MAPPING = {
    "schema_version": "0.2.0",
    "form_definition": "rasens_offer_fields.json",
    "mappings": [
        {
            "canonical_id": "entry_plan.main_activity_category",
            "value_path": "entry_plan.main_activity_category",
            "label": "主たる活動内容",
            "field_id": "select_256097",
            "field_name": "item[1].selectData",
            "input_type": "select",
        },
        {
            "canonical_id": "applicant.birth_date",
            "value_path": "applicant.birth_date",
            "label": "生年月日",
            "field_id": "textData1_256102",
            "field_name": "",
            "input_type": "text",
            "transform": "date_yyyymmdd",
        },
        {
            "canonical_id": "applicant.immigration_history.entries_count",
            "value_path": "applicant.immigration_history.entries_count",
            "label": "過去の出入国歴 回数",
            "field_id": "select_256126",
            "field_name": "item[30].selectData",
            "input_type": "select",
            "visible_when": [
                {
                    "path": "applicant.immigration_history.has_entries",
                    "operator": "==",
                    "value": True,
                }
            ],
        },
        {
            "canonical_id": "employment.activity_details",
            "value_path": "employment.activity_details",
            "label": "活動内容詳細",
            "field_id": "switch_256306",
            "field_name": "item[210].textData",
            "input_type": "textarea",
        },
        {
            "canonical_id": "intermediary.name",
            "value_path": "settings.intermediary.name",
            "label": "取次者 氏名",
            "field_id": "switch_256263",
            "field_name": "item[167].textData",
            "input_type": "text",
            "source_page": "settings",
        },
    ],
}


CASE_DOC = {
    "case_id": "case_test01",
    "workflow_state": "extracted",
    "case_data": {
        "case": {"case_id": "case_test01"},
        "entry_plan": {"main_activity_category": "技術・人文知識・国際業務"},
        "applicant": {
            "birth_date": "1995-03-15",
            "immigration_history": {"has_entries": True, "entries_count": 3},
        },
        "employment": {"activity_details": "システム開発業務に従事"},
    },
    "settings": {
        "intermediary": {
            "name": "取次 太郎",
        },
    },
}


def test_build_rows_from_canonical_case_data():
    source_data = dict(CASE_DOC["case_data"])
    source_data["settings"] = CASE_DOC["settings"]
    rows = build_rows(source_data, MAPPING, FORM_DEFINITIONS)

    assert [row["canonical_path"] for row in rows] == [
        "entry_plan.main_activity_category",
        "applicant.birth_date",
        "applicant.immigration_history.entries_count",
        "employment.activity_details",
        "settings.intermediary.name",
    ]
    assert rows[1]["fill_value"] == "19950315"
    assert rows[1]["required"] is True
    assert rows[3]["input_type"] == "textarea"
    assert rows[4]["source_page"] == "settings"


def test_visible_when_false_skips_row():
    case_doc = {
        **CASE_DOC,
        "case_data": {
            **CASE_DOC["case_data"],
            "applicant": {
                "birth_date": "1995-03-15",
                "immigration_history": {"has_entries": False, "entries_count": 3},
            },
        },
    }

    rows = build_rows(case_doc["case_data"], MAPPING, FORM_DEFINITIONS)

    assert "applicant.immigration_history.entries_count" not in [
        row["canonical_path"] for row in rows
    ]


def test_build_application_data_summary_and_fillable():
    result = build_application_data(CASE_DOC, MAPPING, FORM_DEFINITIONS)

    assert result["case_id"] == "case_test01"
    assert result["fillable"] is True
    assert result["warnings"] == []
    assert result["summary"]["rows_total"] == 5
    assert result["mapping_version"] == "0.2.0"


@pytest.mark.parametrize("workflow_state", ["extracted", "needs_review", "ready_to_fill"])
def test_fillable_workflow_states(workflow_state):
    assert is_fillable_workflow_state(workflow_state) is True

    case_doc = {**CASE_DOC, "workflow_state": workflow_state}

    result = build_application_data(case_doc, MAPPING, FORM_DEFINITIONS)

    assert result["fillable"] is True
    assert result["warnings"] == []
    assert result["summary"]["rows_total"] == 5


@pytest.mark.parametrize(
    "workflow_state",
    ["draft", "extracting", "failed", "extraction_failed", "launch_failed", ""],
)
def test_unfillable_workflow_states_return_rows_for_preview(workflow_state):
    assert is_fillable_workflow_state(workflow_state) is False

    case_doc = {**CASE_DOC, "workflow_state": workflow_state}

    result = build_application_data(case_doc, MAPPING, FORM_DEFINITIONS)

    assert result["fillable"] is False
    assert result["warnings"] == [f"workflow_state is not fillable: {workflow_state or 'unknown'}"]
    assert result["summary"]["rows_total"] == 5


def test_mapping_target_must_match_form_definitions():
    mapping = {
        **MAPPING,
        "mappings": [
            {
                **MAPPING["mappings"][0],
                "field_id": "missing_field",
            }
        ],
    }

    with pytest.raises(ValueError, match="mapping target not found"):
        build_rows(CASE_DOC["case_data"], mapping, FORM_DEFINITIONS)
