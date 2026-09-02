"""RASENS mapping and form definition helpers."""

import pytest

from rasens_definitions import (
    load_default_form_definitions,
    load_default_mapping,
    select_option_texts_for_canonical_id,
)


def _job_category_mapping():
    return {
        "mappings": [
            {
                "canonical_id": "employment.job_category_primary",
                "field_id": "select_job",
                "field_name": "item[205].selectData",
            }
        ],
    }


def _job_category_form_definitions(options):
    return {
        "fields": [
            {
                "controls": [
                    {
                        "field_id": "select_job",
                        "field_name": "item[205].selectData",
                        "input_type": "select",
                        "options": options,
                    }
                ]
            }
        ]
    }


def test_select_option_texts_for_canonical_id_uses_form_definition_master():
    options = select_option_texts_for_canonical_id(
        "employment.job_category_primary",
        load_default_mapping(),
        load_default_form_definitions(),
    )

    assert len(options) == 30
    assert options[0] == "管理業務（経営者を除く） Management work (excluding executives)"
    assert "建築・土木・測量技術 Architecture, civil engineering, surveying techniques" in options
    assert "選択してください" not in options


def test_select_option_texts_for_canonical_id_reads_form_definition_options():
    options = select_option_texts_for_canonical_id(
        "employment.job_category_primary",
        _job_category_mapping(),
        _job_category_form_definitions(
            [
                {"value": "1", "text": "選択してください"},
                {"value": "2", "text": "管理業務 Management work"},
                {"value": "12", "text": "情報処理・通信技術 Information processing"},
            ]
        ),
    )

    assert options == (
        "管理業務 Management work",
        "情報処理・通信技術 Information processing",
    )


def test_select_option_texts_for_canonical_id_fails_when_control_is_missing():
    with pytest.raises(ValueError, match="form definition target not found"):
        select_option_texts_for_canonical_id(
            "employment.job_category_primary",
            _job_category_mapping(),
            {"fields": [{"controls": []}]},
        )


def test_select_option_texts_for_canonical_id_fails_when_no_real_options_exist():
    with pytest.raises(ValueError, match="select options not found"):
        select_option_texts_for_canonical_id(
            "employment.job_category_primary",
            _job_category_mapping(),
            _job_category_form_definitions([{"value": "1", "text": "選択してください"}]),
        )
