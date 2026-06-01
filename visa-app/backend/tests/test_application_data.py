"""application_data generator tests."""

import copy
import json
from pathlib import Path

import pytest

from application_data import (
    build_application_data,
    build_display_case_data,
    build_rows,
    is_fillable_workflow_state,
    transform_value,
)


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


def test_visible_when_accepts_boolean_strings():
    case_data = {
        **CASE_DOC["case_data"],
        "applicant": {
            "birth_date": "1995-03-15",
            "immigration_history": {"has_entries": "true", "entries_count": 3},
        },
    }

    rows = build_rows(case_data, MAPPING, FORM_DEFINITIONS)

    assert "applicant.immigration_history.entries_count" in [
        row["canonical_path"] for row in rows
    ]


def test_visible_when_accepts_native_boolean_and_integer_zero_value():
    case_data = {
        **CASE_DOC["case_data"],
        "applicant": {
            "birth_date": "1995-03-15",
            "immigration_history": {"has_entries": True, "entries_count": 0},
        },
    }

    rows = build_rows(case_data, MAPPING, FORM_DEFINITIONS)
    row = next(
        row
        for row in rows
        if row["canonical_path"] == "applicant.immigration_history.entries_count"
    )

    assert row["display_value"] == "0"
    assert row["fill_value"] == "0"


def test_build_application_data_summary_and_fillable():
    result = build_application_data(CASE_DOC, MAPPING, FORM_DEFINITIONS)

    assert result["case_id"] == "case_test01"
    assert result["fillable"] is True
    assert result["warnings"] == []
    assert result["summary"]["rows_total"] == 5
    assert result["mapping_version"] == "0.2.0"


def test_required_missing_value_does_not_block_partial_fill():
    case_doc = copy.deepcopy(CASE_DOC)
    del case_doc["case_data"]["employment"]["activity_details"]

    result = build_application_data(case_doc, MAPPING, FORM_DEFINITIONS)

    assert result["fillable"] is True
    assert result["warnings"] == []
    assert result["summary"]["rows_total"] == 4
    assert result["summary"]["rows_skipped_empty"] == 1
    assert "employment.activity_details" not in [
        row["canonical_path"] for row in result["rows"]
    ]


def test_transform_contract_type_for_rasens_radio():
    assert transform_value("fixed term contract employee", "contract_type") == "雇用 Employment"
    assert transform_value("請負", "contract_type") == "請負 Service contract"


def test_transform_education_values_for_rasens_options():
    assert transform_value("TRIBHUVAN UNIVERSITY", "education_country") == "外国 Foreign country"
    assert transform_value("東京大学", "education_country") == "本邦 Japan"
    assert transform_value("The University of Tokyo", "education_country") == "本邦 Japan"
    assert transform_value("Bachelor", "education_level") == "大学 Bachelor"
    assert transform_value("Architectural Engineering", "major_field_university") == "工学 Engineer"


def test_transform_number_and_date_values():
    assert transform_value("260,000円", "digits") == "260000"
    assert transform_value("2026-04-01", "date_yyyymmdd") == "20260401"
    assert transform_value("2026年4月1日", "date_yyyymmdd") == "20260401"
    assert transform_value("2026年4月", "date_yyyymm") == "202604"
    assert transform_value("2026年4月", "date_yyyy") == "2026"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "有 Yes"),
        ("true", "有 Yes"),
        ("有", "有 Yes"),
        ("あり", "有 Yes"),
        ("1", "有 Yes"),
        (False, "無 No"),
        ("false", "無 No"),
        ("無", "無 No"),
        ("なし", "無 No"),
        ("0", "無 No"),
    ],
)
def test_transform_boolean_yes_no_values(value, expected):
    assert transform_value(value, "boolean_yes_no") == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "月不詳 Unknown(Month)"),
        ("true", "月不詳 Unknown(Month)"),
        ("有", "月不詳 Unknown(Month)"),
        (False, "不明な点は無い No unclear points"),
        ("false", "不明な点は無い No unclear points"),
        ("無", "不明な点は無い No unclear points"),
    ],
)
def test_transform_month_unknown_values(value, expected):
    assert transform_value(value, "month_unknown") == expected


def test_repeated_rows_are_visible_only_when_parent_boolean_is_true():
    form_definitions = {
        "fields": [
            {
                "section": "身分事項",
                "no": "21.1",
                "label": "在日親族及び同居者 有無",
                "required": True,
                "controls": [{"field_id": "", "field_name": "item[40].selectData", "input_type": "radio"}],
            },
            {
                "section": "身分事項",
                "no": "21.3",
                "label": "在日親族及び同居者 氏名01",
                "required": True,
                "controls": [{"field_id": "switch_256139", "field_name": "item[43].textData", "input_type": "text"}],
            },
            {
                "section": "申請人に関する情報等",
                "no": "",
                "label": "職歴の有無",
                "required": True,
                "controls": [{"field_id": "", "field_name": "item[101].selectData", "input_type": "radio"}],
            },
            {
                "section": "申請人に関する情報等",
                "no": "26.1",
                "label": "職歴 入社月不詳01",
                "required": True,
                "controls": [{"field_id": "", "field_name": "item[104].selectData", "input_type": "radio"}],
            },
        ],
    }
    mapping = {
        "mappings": [
            {
                "canonical_id": "applicant.family.has_japan_relatives_or_cohabitants",
                "value_path": "applicant.family.has_japan_relatives_or_cohabitants",
                "label": "在日親族及び同居者 有無",
                "field_id": "",
                "field_name": "item[40].selectData",
                "input_type": "radio",
                "transform": "boolean_yes_no",
            },
            {
                "canonical_id": "applicant.family.japan_relatives_or_cohabitants.0.name",
                "value_path": "applicant.family.japan_relatives_or_cohabitants.0.name",
                "label": "在日親族及び同居者 氏名01",
                "field_id": "switch_256139",
                "field_name": "item[43].textData",
                "input_type": "text",
                "visible_when": [
                    {
                        "path": "applicant.family.has_japan_relatives_or_cohabitants",
                        "operator": "==",
                        "value": True,
                    }
                ],
            },
            {
                "canonical_id": "applicant.has_employment_history",
                "value_path": "applicant.has_employment_history",
                "label": "職歴の有無",
                "field_id": "",
                "field_name": "item[101].selectData",
                "input_type": "radio",
                "transform": "boolean_yes_no",
            },
            {
                "canonical_id": "applicant.employment_history.0.start_month_unknown",
                "value_path": "applicant.employment_history.0.start_month_unknown",
                "label": "職歴 入社月不詳01",
                "field_id": "",
                "field_name": "item[104].selectData",
                "input_type": "radio",
                "transform": "month_unknown",
                "visible_when": [
                    {
                        "path": "applicant.has_employment_history",
                        "operator": "==",
                        "value": True,
                    }
                ],
            },
        ]
    }
    case_doc = {
        "case_id": "case_repeated",
        "workflow_state": "extracted",
        "case_data": {
            "applicant": {
                "family": {
                    "has_japan_relatives_or_cohabitants": "true",
                    "japan_relatives_or_cohabitants": [{"name": "YAMADA TARO"}],
                },
                "has_employment_history": "true",
                "employment_history": [{"start_month_unknown": False}],
            }
        },
    }

    rows = build_application_data(case_doc, mapping, form_definitions)["rows"]

    assert {row["canonical_path"]: row["fill_value"] for row in rows} == {
        "applicant.family.has_japan_relatives_or_cohabitants": "有 Yes",
        "applicant.family.japan_relatives_or_cohabitants.0.name": "YAMADA TARO",
        "applicant.has_employment_history": "有 Yes",
        "applicant.employment_history.0.start_month_unknown": "不明な点は無い No unclear points",
    }


def test_application_defaults_generate_rasens_rows():
    form_definitions = {
        "fields": [
            {
                "section": "身分事項",
                "no": "13.1",
                "label": "上陸予定港",
                "required": True,
                "controls": [{"field_id": "select_256119", "field_name": "item[23].selectData", "input_type": "select"}],
            },
            {
                "section": "身分事項",
                "no": "14.1",
                "label": "滞在予定期間 年数",
                "required": True,
                "controls": [{"field_id": "select_256121", "field_name": "item[25].selectData", "input_type": "select"}],
            },
            {
                "section": "身分事項",
                "no": "15",
                "label": "同伴者の有無",
                "required": True,
                "controls": [{"field_id": "", "field_name": "item[27].selectData", "input_type": "radio"}],
            },
            {
                "section": "所属機関に関する情報等",
                "no": "3.2",
                "label": "法人番号の有無",
                "required": True,
                "controls": [{"field_id": "", "field_name": "item[176].selectData", "input_type": "radio"}],
            },
            {
                "section": "所属機関に関する情報等",
                "no": "2",
                "label": "契約の形態",
                "required": True,
                "controls": [{"field_id": "radioList_256270_1", "field_name": "item[174].selectData", "input_type": "radio"}],
            },
            {
                "section": "所属機関に関する情報等",
                "no": "5.1",
                "label": "就労予定期間",
                "required": True,
                "controls": [{"field_id": "", "field_name": "item[197].selectData", "input_type": "radio"}],
            },
        ],
    }
    mapping = {
        "mappings": [
            {
                "canonical_id": "entry_plan.planned_port",
                "value_path": "entry_plan.planned_port",
                "label": "上陸予定港",
                "field_id": "select_256119",
                "field_name": "item[23].selectData",
                "input_type": "select",
            },
            {
                "canonical_id": "entry_plan.planned_period_years",
                "value_path": "entry_plan.planned_period_years",
                "label": "滞在予定期間 年数",
                "field_id": "select_256121",
                "field_name": "item[25].selectData",
                "input_type": "select",
            },
            {
                "canonical_id": "applicant.family.has_accompanying_members",
                "value_path": "applicant.family.has_accompanying_members",
                "label": "同伴者の有無",
                "field_id": "",
                "field_name": "item[27].selectData",
                "input_type": "radio",
                "transform": "boolean_yes_no",
            },
            {
                "canonical_id": "employer.has_corporate_number",
                "value_path": "employer.has_corporate_number",
                "label": "法人番号の有無",
                "field_id": "",
                "field_name": "item[176].selectData",
                "input_type": "radio",
                "transform": "boolean_yes_no",
            },
            {
                "canonical_id": "employment.contract_type",
                "value_path": "employment.contract_type",
                "label": "契約の形態",
                "field_id": "radioList_256270_1",
                "field_name": "item[174].selectData",
                "input_type": "radio",
                "transform": "contract_type",
            },
            {
                "canonical_id": "employment.employment_period_type",
                "value_path": "employment.employment_period_type",
                "label": "就労予定期間",
                "field_id": "",
                "field_name": "item[197].selectData",
                "input_type": "radio",
                "transform": "employment_period_type",
            },
        ]
    }
    case_doc = {
        "case_id": "case_defaults",
        "workflow_state": "extracted",
        "case_data": {
            "employer": {
                "address": "東京都新宿区西新宿二丁目",
                "corporate_number": "8011001039242",
            }
        },
    }

    rows = build_application_data(case_doc, mapping, form_definitions)["rows"]

    assert {row["canonical_path"]: row["fill_value"] for row in rows} == {
        "entry_plan.planned_port": "羽田空港(HND) Haneda Airport",
        "entry_plan.planned_period_years": "5",
        "applicant.family.has_accompanying_members": "無 No",
        "employer.has_corporate_number": "有 Yes",
        "employment.contract_type": "雇用 Employment",
        "employment.employment_period_type": "定めあり Fixed",
    }


def test_deportation_rows_visible_when_boolean_is_string():
    form_definitions = {
        "fields": [
            {
                "section": "身分事項",
                "no": "20.1",
                "label": "退去強制・出国命令歴",
                "required": True,
                "controls": [{"field_id": "", "field_name": "item[36].selectData", "input_type": "radio"}],
            },
            {
                "section": "身分事項",
                "no": "20.2",
                "label": "退去強制・出国命令歴 回数",
                "required": False,
                "controls": [{"field_id": "select_256132", "field_name": "item[37].selectData", "input_type": "select"}],
            },
            {
                "section": "身分事項",
                "no": "20.3",
                "label": "直近の退去強制・出国命令年月日",
                "required": False,
                "controls": [{"field_id": "textData1_256133", "field_name": "", "input_type": "text"}],
            },
        ],
    }
    mapping = {
        "mappings": [
            {
                "canonical_id": "applicant.immigration_history.deportation_or_departure_order",
                "value_path": "applicant.immigration_history.deportation_or_departure_order",
                "label": "退去強制・出国命令歴",
                "field_id": "",
                "field_name": "item[36].selectData",
                "input_type": "radio",
                "transform": "boolean_yes_no",
            },
            {
                "canonical_id": "applicant.immigration_history.deportation_count",
                "value_path": "applicant.immigration_history.deportation_count",
                "label": "退去強制・出国命令歴 回数",
                "field_id": "select_256132",
                "field_name": "item[37].selectData",
                "input_type": "select",
                "visible_when": [
                    {
                        "path": "applicant.immigration_history.deportation_or_departure_order",
                        "operator": "==",
                        "value": True,
                    }
                ],
            },
            {
                "canonical_id": "applicant.immigration_history.deportation_latest",
                "value_path": "applicant.immigration_history.deportation_latest",
                "label": "直近の退去強制・出国命令年月日",
                "field_id": "textData1_256133",
                "field_name": "",
                "input_type": "text",
                "transform": "date_yyyymmdd",
                "visible_when": [
                    {
                        "path": "applicant.immigration_history.deportation_or_departure_order",
                        "operator": "==",
                        "value": True,
                    }
                ],
            },
        ]
    }
    case_doc = {
        "case_id": "case_deportation",
        "workflow_state": "extracted",
        "case_data": {
            "applicant": {
                "immigration_history": {
                    "deportation_or_departure_order": "true",
                    "deportation_count": "1",
                    "deportation_latest": "2024-01-02",
                }
            }
        },
    }

    rows = build_application_data(case_doc, mapping, form_definitions)["rows"]

    assert {row["canonical_path"]: row["fill_value"] for row in rows} == {
        "applicant.immigration_history.deportation_or_departure_order": "有 Yes",
        "applicant.immigration_history.deportation_count": "1",
        "applicant.immigration_history.deportation_latest": "20240102",
    }


def test_display_case_data_includes_proxy_defaults():
    result = build_display_case_data({
        "employer": {
            "name": "株式会社フジタ",
            "postal_code": "151-8570",
            "address": "東京都渋谷区千駄ヶ谷四丁目25番2号",
            "phone": "03-3402-1911",
        }
    })

    assert result["proxy"] == {
        "name": "株式会社フジタ",
        "relationship": "所属機関等契約先",
        "postal_code": "151-8570",
        "address": "東京都渋谷区千駄ヶ谷四丁目25番2号",
        "phone": "03-3402-1911",
    }


def test_display_case_data_includes_intermediary_settings():
    result = build_display_case_data(
        {"applicant": {}},
        {
            "intermediary": {
                "organization": "中央ビジネスグループ",
                "name": "太田",
                "postal_code": "5300001",
                "address": "大阪府大阪市北区梅田1-1-1",
                "phone": "0660000000",
            }
        },
    )

    assert result["settings"]["intermediary"]["name"] == "太田"
    assert result["settings"]["intermediary"]["organization"] == "中央ビジネスグループ"


def test_build_application_data_uses_intermediary_env_fallback(monkeypatch):
    monkeypatch.setenv("INTERMEDIARY_NAME", "太田")
    case_doc = {
        key: value
        for key, value in CASE_DOC.items()
        if key != "settings"
    }

    rows = build_application_data(case_doc, MAPPING, FORM_DEFINITIONS)["rows"]

    assert {
        row["canonical_path"]: row["fill_value"]
        for row in rows
        if row["canonical_path"].startswith("settings.intermediary")
    } == {"settings.intermediary.name": "太田"}


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


def test_backend_and_extension_mapping_files_are_in_sync():
    workspace = Path(__file__).resolve().parents[3]
    backend_mapping = workspace / "visa-app/backend/data/mappings/rasens_offer_mapping_v2.json"
    extension_mapping = workspace / "rasens-autofill/data/mappings/rasens_offer_mapping_v2.json"

    assert json.loads(backend_mapping.read_text()) == json.loads(extension_mapping.read_text())
