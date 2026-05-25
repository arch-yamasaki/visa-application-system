"""autofill_adapter.adapt() のユニットテスト。"""

import pytest

from autofill_adapter import adapt, _get, _set, _build_education_array, _normalize_date


# ---------- テスト用データ -----------------------------------------------

_CASE_DOC = {
    "case_id": "case_test01",
    "workflow_state": "needs_review",
}

_DISPLAY_CASE_DATA_FULL = {
    "applicant": {
        "nationality": "ベトナム",
        "date_of_birth": "1995-03-15",
        "gender": "male",
        "place_of_birth": "ハノイ",
        "name_roman": "NGUYEN VAN A",
        "marital_status": "single",
        "occupation": "エンジニア",
        "home_country_address": "123 Hanoi Street",
        "japan_postal_code": "160-0022",
        "japan_address": "東京都新宿区新宿1-1-1",
        "japan_phone": "03-1234-5678",
        "japan_mobile": "090-1234-5678",
        "email": "nguyen@example.com",
    },
    "passport": {
        "number": "C1234567",
        "expiry_date": "2030-12-31",
    },
    "employer": {
        "name": "株式会社テスト",
        "corporate_number": "1234567890123",
        "office_name": "本社",
        "employment_insurance_no": "1234-567890-1",
        "postal_code": "100-0001",
        "address": "東京都千代田区千代田1-1",
        "phone": "03-9876-5432",
        "capital_jpy": "10000000",
        "annual_sales_jpy": "500000000",
        "employee_count": "50",
        "foreign_employee_count": "10",
        "technical_intern_count": "0",
        "industry_primary": "情報通信業",
    },
    "immigration_history": {
        "has_criminal_record": False,
        "has_entries": True,
        "entries_count": 3,
        "latest_entry_start": "2024-01-10",
        "latest_entry_end": "2024-04-10",
        "has_deportation": False,
        "has_prior_coe": True,
        "prior_coe_count": 1,
        "prior_coe_denial_count": 0,
        "deportation_count": 0,
    },
    "application": {
        "has_accompanying": False,
        "purpose_of_entry": "就労",
        "planned_entry_date": "2026-08-01",
        "planned_port": "成田空港",
        "planned_period_years": "5",
        "planned_period_months": "0",
        "visa_application_location": "在ベトナム日本国大使館",
    },
    "activity_details": {
        "description": "システム開発業務に従事",
    },
    "education": {
        "level": "university",
        "school_name": "ハノイ工科大学",
        "graduation_date": "2018-06-30",
    },
    "major": {
        "field": "情報工学",
    },
    "contract": {
        "type": "full_time",
        "start_date": "2026-09-01",
    },
    "employment_conditions": {
        "monthly_salary": 250000,
    },
    "it_qualification": {
        "has_it_qualification": True,
    },
}


# ---------- ヘルパー関数テスト -------------------------------------------


class TestGet:
    def test_simple_path(self):
        assert _get({"a": {"b": 1}}, "a.b") == 1

    def test_missing_path(self):
        assert _get({"a": {}}, "a.b") is None

    def test_deep_missing(self):
        assert _get({}, "a.b.c") is None

    def test_non_dict_intermediate(self):
        assert _get({"a": 42}, "a.b") is None


class TestSet:
    def test_simple_set(self):
        d = {}
        _set(d, "a.b", 1)
        assert d == {"a": {"b": 1}}

    def test_nested_set(self):
        d = {}
        _set(d, "a.b.c", "v")
        assert d == {"a": {"b": {"c": "v"}}}

    def test_preserves_existing(self):
        d = {"a": {"x": 1}}
        _set(d, "a.y", 2)
        assert d == {"a": {"x": 1, "y": 2}}


class TestBuildEducationArray:
    def test_single_education_with_major(self):
        src = {
            "education": {"level": "university", "school_name": "東大"},
            "major": {"field": "工学"},
        }
        result = _build_education_array(src)
        assert result is not None
        assert len(result) == 1
        assert result[0]["school_name"] == "東大"
        assert result[0]["major"] == "工学"

    def test_major_field_other(self):
        src = {
            "education": {"level": "university", "school_name": "早大"},
            "major": {"field_other": "国際関係"},
        }
        result = _build_education_array(src)
        assert result[0]["major"] == "国際関係"

    def test_no_major(self):
        src = {
            "education": {"level": "university", "school_name": "京大"},
        }
        result = _build_education_array(src)
        assert result is not None
        assert "major" not in result[0]

    def test_no_education(self):
        assert _build_education_array({}) is None

    def test_education_not_dict(self):
        assert _build_education_array({"education": "string"}) is None


# ---------- adapt() メインテスト ------------------------------------------


class TestAdapt:
    """adapt() の入出力変換を検証する。"""

    def test_schema_version(self):
        result = adapt({}, {"case_id": "c1"})
        assert result["schema_version"] == "1.0"

    def test_case_section(self):
        result = adapt({}, _CASE_DOC)
        assert result["case"]["case_id"] == "case_test01"
        assert result["case"]["workflow_state"] == "needs_review"
        assert result["case"]["application_type"] == "certificate_of_eligibility"
        assert result["case"]["target_status"] == "engineer_humanities_international"

    def test_defaults(self):
        result = adapt({}, _CASE_DOC)
        assert result["application"]["desired_status_label"] == "技術・人文知識・国際業務"

    # --- フィールドリネーム (_RENAMES) テスト ---

    def test_rename_nationality(self):
        src = {"applicant": {"nationality": "ベトナム"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["nationality_region"] == "ベトナム"

    def test_rename_birth_date(self):
        src = {"applicant": {"date_of_birth": "1995-03-15"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["birth_date"] == "1995-03-15"

    def test_rename_sex(self):
        src = {"applicant": {"gender": "male"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["sex"] == "male"

    def test_rename_birth_place(self):
        src = {"applicant": {"place_of_birth": "ハノイ"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["birth_place"] == "ハノイ"

    def test_rename_employment_insurance(self):
        src = {"employer": {"employment_insurance_no": "1234"}}
        result = adapt(src, _CASE_DOC)
        assert result["employer"]["employment_insurance_office_number"] == "1234"

    def test_rename_criminal_record(self):
        src = {"immigration_history": {"has_criminal_record": False}}
        result = adapt(src, _CASE_DOC)
        assert result["immigration_history"]["criminal_record"] is False

    # --- ネスト変換 (_NESTS) テスト ---

    def test_nest_japan_contact(self):
        src = {
            "applicant": {
                "japan_postal_code": "160-0022",
                "japan_address": "東京都新宿区",
                "japan_phone": "03-1234",
                "japan_mobile": "090-1234",
                "email": "test@example.com",
            }
        }
        result = adapt(src, _CASE_DOC)
        contact = result["applicant"]["japan_contact"]
        assert contact["postal_code"] == "160-0022"
        assert contact["address"] == "東京都新宿区"
        assert contact["phone"] == "03-1234"
        assert contact["mobile"] == "090-1234"
        assert contact["email"] == "test@example.com"

    def test_nest_latest_entry(self):
        src = {
            "immigration_history": {
                "latest_entry_start": "2024-01-10",
                "latest_entry_end": "2024-04-10",
            }
        }
        result = adapt(src, _CASE_DOC)
        entry = result["immigration_history"]["latest_entry"]
        assert entry["start_date"] == "2024-01-10"
        assert entry["end_date"] == "2024-04-10"

    def test_nest_deportation(self):
        src = {"immigration_history": {"has_deportation": False}}
        result = adapt(src, _CASE_DOC)
        assert result["immigration_history"]["deportation_or_departure_order"] is False

    # --- 構造移動 (_MOVES) テスト ---

    def test_move_prior_coe(self):
        src = {
            "immigration_history": {
                "has_prior_coe": True,
                "prior_coe_count": 2,
                "prior_coe_denial_count": 1,
            }
        }
        result = adapt(src, _CASE_DOC)
        coe = result["immigration_history"]["prior_coe_applications"]
        assert coe["has_history"] is True
        assert coe["count"] == 2
        assert coe["denial_count"] == 1

    def test_move_has_accompanying(self):
        src = {"application": {"has_accompanying": True}}
        result = adapt(src, _CASE_DOC)
        assert result["family"]["has_accompanying_members"] is True

    def test_move_activity_details(self):
        src = {"activity_details": {"description": "開発業務"}}
        result = adapt(src, _CASE_DOC)
        assert result["application"]["activity_details"] == "開発業務"

    # --- パススルーセクション テスト ---

    def test_passthrough_passport(self):
        src = {"passport": {"number": "C123", "expiry_date": "2030-12-31"}}
        result = adapt(src, _CASE_DOC)
        assert result["passport"]["number"] == "C123"
        assert result["passport"]["expiry_date"] == "2030-12-31"

    def test_passthrough_contract(self):
        src = {"contract": {"type": "full_time"}}
        result = adapt(src, _CASE_DOC)
        assert result["contract"]["type"] == "full_time"

    def test_passthrough_employment_conditions(self):
        src = {"employment_conditions": {"monthly_salary": 250000}}
        result = adapt(src, _CASE_DOC)
        assert result["employment_conditions"]["monthly_salary"] == 250000

    def test_passthrough_it_qualification(self):
        src = {"it_qualification": {"has_it_qualification": True}}
        result = adapt(src, _CASE_DOC)
        assert result["it_qualification"]["has_it_qualification"] is True

    # --- applicant 直接コピー テスト ---

    def test_applicant_name_roman(self):
        src = {"applicant": {"name_roman": "NGUYEN VAN A"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["name_roman"] == "NGUYEN VAN A"

    def test_applicant_marital_status(self):
        src = {"applicant": {"marital_status": "single"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["marital_status"] == "single"

    # --- employer コピー テスト ---

    def test_employer_fields_copy(self):
        src = {
            "employer": {
                "name": "株式会社テスト",
                "phone": "03-9876",
                "capital_jpy": "10000000",
            }
        }
        result = adapt(src, _CASE_DOC)
        assert result["employer"]["name"] == "株式会社テスト"
        assert result["employer"]["phone"] == "03-9876"
        assert result["employer"]["capital_jpy"] == "10000000"

    def test_employer_insurance_no_not_duplicated(self):
        """employment_insurance_no はリネームされるので、元キーは残らない。"""
        src = {"employer": {"employment_insurance_no": "1234", "name": "ABC"}}
        result = adapt(src, _CASE_DOC)
        assert "employment_insurance_no" not in result["employer"]
        assert result["employer"]["employment_insurance_office_number"] == "1234"

    def test_employer_extraction_keys_renamed(self):
        """Gemini抽出の employer キー名が autofill スキーマに合わせてリネームされる。"""
        src = {
            "employer": {
                "company_name": "株式会社フジタ",
                "capital": "14022055010",
                "sales": "499852000000",
                "employees": "3393",
                "phone": "03-1234-5678",
            }
        }
        result = adapt(src, _CASE_DOC)
        assert result["employer"]["name"] == "株式会社フジタ"
        assert result["employer"]["capital_jpy"] == "14022055010"
        assert result["employer"]["annual_sales_jpy"] == "499852000000"
        assert result["employer"]["employee_count"] == "3393"
        assert result["employer"]["phone"] == "03-1234-5678"
        # 元キーは残らない
        for old_key in ("company_name", "capital", "sales", "employees"):
            assert old_key not in result["employer"]

    # --- immigration_history 直接コピー テスト ---

    def test_immigration_history_direct(self):
        src = {
            "immigration_history": {
                "has_entries": True,
                "entries_count": 3,
            }
        }
        result = adapt(src, _CASE_DOC)
        assert result["immigration_history"]["has_entries"] is True
        assert result["immigration_history"]["entries_count"] == 3

    # --- application 直接コピー テスト ---

    def test_application_fields(self):
        src = {
            "application": {
                "purpose_of_entry": "就労",
                "planned_entry_date": "2026-08-01",
                "planned_port": "成田空港",
                "planned_period_years": "5",
                "planned_period_months": "0",
                "visa_application_location": "在ベトナム日本国大使館",
            }
        }
        result = adapt(src, _CASE_DOC)
        assert result["application"]["purpose_of_entry"] == "就労"
        assert result["application"]["planned_port"] == "成田空港"
        assert result["application"]["visa_application_location"] == "在ベトナム日本国大使館"

    # --- education 変換 テスト ---

    def test_education_array(self):
        src = {
            "education": {"level": "university", "school_name": "ハノイ工科大学"},
            "major": {"field": "情報工学"},
        }
        result = adapt(src, _CASE_DOC)
        assert isinstance(result["education"], list)
        assert len(result["education"]) == 1
        assert result["education"][0]["school_name"] == "ハノイ工科大学"
        assert result["education"][0]["major"] == "情報工学"

    def test_no_education_section(self):
        result = adapt({}, _CASE_DOC)
        assert "education" not in result

    # --- 全フィールド統合テスト ---

    def test_full_conversion(self):
        """全フィールドを含む入力で adapt() の統合的な変換を検証する。"""
        result = adapt(_DISPLAY_CASE_DATA_FULL, _CASE_DOC)

        # schema_version
        assert result["schema_version"] == "1.0"

        # case
        assert result["case"]["case_id"] == "case_test01"

        # applicant renames
        assert result["applicant"]["nationality_region"] == "ベトナム"
        assert result["applicant"]["birth_date"] == "1995-03-15"
        assert result["applicant"]["sex"] == "male"
        assert result["applicant"]["birth_place"] == "ハノイ"

        # applicant nests
        assert result["applicant"]["japan_contact"]["postal_code"] == "160-0022"
        assert result["applicant"]["japan_contact"]["email"] == "nguyen@example.com"

        # applicant direct
        assert result["applicant"]["name_roman"] == "NGUYEN VAN A"
        assert result["applicant"]["marital_status"] == "single"

        # passport passthrough
        assert result["passport"]["number"] == "C1234567"

        # employer (rename + copy)
        assert result["employer"]["employment_insurance_office_number"] == "1234-567890-1"
        assert result["employer"]["name"] == "株式会社テスト"
        assert "employment_insurance_no" not in result["employer"]

        # immigration_history (rename + nest + move + direct)
        assert result["immigration_history"]["criminal_record"] is False
        assert result["immigration_history"]["latest_entry"]["start_date"] == "2024-01-10"
        assert result["immigration_history"]["prior_coe_applications"]["has_history"] is True
        assert result["immigration_history"]["has_entries"] is True

        # application (move + direct)
        assert result["application"]["activity_details"] == "システム開発業務に従事"
        assert result["application"]["planned_port"] == "成田空港"
        assert result["application"]["desired_status_label"] == "技術・人文知識・国際業務"

        # family (move)
        assert result["family"]["has_accompanying_members"] is False

        # education (array conversion)
        assert len(result["education"]) == 1
        assert result["education"][0]["major"] == "情報工学"

        # passthrough sections
        assert result["contract"]["type"] == "full_time"
        assert result["employment_conditions"]["monthly_salary"] == 250000
        assert result["it_qualification"]["has_it_qualification"] is True


# ---------- エッジケース・エラーテスト -------------------------------------------


class TestAdaptEdgeCases:
    def test_empty_display_data(self):
        """空の display_case_data でもクラッシュしない。"""
        result = adapt({}, _CASE_DOC)
        assert result["schema_version"] == "1.0"
        assert result["case"]["case_id"] == "case_test01"

    def test_missing_case_id(self):
        """case_doc に case_id がない場合は空文字。"""
        result = adapt({}, {})
        assert result["case"]["case_id"] == ""

    def test_none_values_ignored(self):
        """None 値のフィールドはコピーされない。"""
        src = {"applicant": {"name_roman": None}}
        result = adapt(src, _CASE_DOC)
        assert "name_roman" not in result.get("applicant", {})

    def test_partial_applicant(self):
        """一部の applicant フィールドのみ存在するケース。"""
        src = {"applicant": {"nationality": "中国"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["nationality_region"] == "中国"
        # 他のリネーム対象は存在しない
        assert "birth_date" not in result["applicant"]

    def test_partial_immigration_history(self):
        """immigration_history の一部フィールドのみ。"""
        src = {"immigration_history": {"has_entries": False}}
        result = adapt(src, _CASE_DOC)
        assert result["immigration_history"]["has_entries"] is False
        assert "latest_entry" not in result["immigration_history"]

    def test_workflow_state_default(self):
        """workflow_state がない場合は draft。"""
        result = adapt({}, {"case_id": "c1"})
        assert result["case"]["workflow_state"] == "draft"


# ---------- 日付正規化テスト ------------------------------------------------


class TestNormalizeDate:
    """_normalize_date() の単体テスト。"""

    def test_iso_passthrough(self):
        assert _normalize_date("2024-12-28") == "2024-12-28"

    def test_dmy_named_month(self):
        assert _normalize_date("28/December/2024") == "2024-12-28"

    def test_dmy_named_month_uppercase(self):
        assert _normalize_date("12/JULY/1998") == "1998-07-12"

    def test_mdy_named_month(self):
        assert _normalize_date("December 28, 2024") == "2024-12-28"

    def test_dmy_numeric(self):
        assert _normalize_date("28/12/2024") == "2024-12-28"

    def test_empty(self):
        assert _normalize_date("") == ""

    def test_unknown_format_passthrough(self):
        assert _normalize_date("sometext") == "sometext"

    def test_single_digit_day(self):
        assert _normalize_date("5/March/2023") == "2023-03-05"


class TestAdaptDateNormalization:
    """adapt() が日付フィールドを YYYY-MM-DD に正規化することを検証。"""

    def test_birth_date_named_month(self):
        src = {"applicant": {"date_of_birth": "28/December/2024"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["birth_date"] == "2024-12-28"

    def test_passport_expiry_named_month(self):
        src = {"passport": {"expiry_date": "15/January/2030"}}
        result = adapt(src, _CASE_DOC)
        assert result["passport"]["expiry_date"] == "2030-01-15"

    def test_education_graduation_date(self):
        src = {
            "education": {"level": "university", "school_name": "X大学",
                          "graduation_date": "30/June/2018"},
        }
        result = adapt(src, _CASE_DOC)
        assert result["education"][0]["graduation_date"] == "2018-06-30"

    def test_iso_date_unchanged(self):
        src = {"applicant": {"date_of_birth": "1995-03-15"}}
        result = adapt(src, _CASE_DOC)
        assert result["applicant"]["birth_date"] == "1995-03-15"
