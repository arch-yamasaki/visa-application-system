"""API の org スコーピングのテスト。

Firestore と認証を fake に差し替え、TestClient で
「認証必須」「org 単位のデータ分離」を検証する。
"""

import copy

import pytest
from fastapi.testclient import TestClient

import main
from auth import AuthUser, require_user

ORG_A = AuthUser(uid="user_a", email="a@example.com", org_id="org_a", role="member")
ORG_A_ADMIN = AuthUser(uid="admin_a", email="admin@example.com", org_id="org_a", role="admin")
ORG_B = AuthUser(uid="user_b", email="b@example.com", org_id="org_b", role="member")


class FakeDoc:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class FakeDocumentRef:
    def __init__(self, docs: dict, doc_id: str):
        self._docs = docs
        self._id = doc_id

    def get(self):
        return FakeDoc(self._docs.get(self._id))

    def set(self, data):
        self._docs[self._id] = data

    def update(self, updates):
        self._docs[self._id].update(updates)


class FakeCollection:
    def __init__(self, docs: dict, filters=()):
        self._docs = docs
        self._filters = filters

    def document(self, doc_id):
        return FakeDocumentRef(self._docs, doc_id)

    def where(self, filter):
        return FakeCollection(self._docs, (*self._filters, filter))

    def stream(self):
        for data in self._docs.values():
            if all(data.get(f.field_path) == f.value for f in self._filters):
                yield FakeDoc(data)


class FakeFirestore:
    def __init__(self):
        self.collections: dict[str, dict] = {"cases": {}, "sessions": {}, "org_settings": {}}

    def collection(self, name):
        return FakeCollection(self.collections[name])


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeFirestore()
    monkeypatch.setattr(main, "db", db)
    return db


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def login_as(user: AuthUser):
    main.app.dependency_overrides[require_user] = lambda: user


def test_api_requires_auth(client, fake_db):
    assert client.get("/cases").status_code == 401
    assert client.post("/cases", json={}).status_code == 401
    assert client.get("/sessions").status_code == 401
    assert client.get("/cases/case_x/application-data").status_code == 401


def test_create_case_records_org_and_owner(client, fake_db):
    login_as(ORG_A)
    res = client.post("/cases", json={})
    assert res.status_code == 200

    case_id = res.json()["case_id"]
    stored = fake_db.collections["cases"][case_id]
    assert stored["org_id"] == "org_a"
    assert stored["owner_uid"] == "user_a"


def test_list_cases_returns_only_own_org(client, fake_db):
    login_as(ORG_A)
    case_id = client.post("/cases", json={}).json()["case_id"]

    assert [c["case_id"] for c in client.get("/cases").json()] == [case_id]

    login_as(ORG_B)
    assert client.get("/cases").json() == []


def test_get_case_of_other_org_is_404(client, fake_db):
    login_as(ORG_A)
    case_id = client.post("/cases", json={}).json()["case_id"]

    assert client.get(f"/cases/{case_id}").status_code == 200

    login_as(ORG_B)
    assert client.get(f"/cases/{case_id}").status_code == 404
    assert client.patch(f"/cases/{case_id}", json={"workflow_state": "draft"}).status_code == 404
    assert client.get(f"/cases/{case_id}/documents").status_code == 404
    assert client.get(f"/cases/{case_id}/application-data").status_code == 404


def test_patch_rejects_case_level_settings(client, fake_db):
    login_as(ORG_A)
    case_id = client.post("/cases", json={}).json()["case_id"]

    response = client.patch(
        f"/cases/{case_id}",
        json={"settings": {"intermediary": {"name": "試験　太郎"}}},
    )

    assert response.status_code == 400
    assert "settings" not in fake_db.collections["cases"][case_id]


def test_patch_rejects_settings_embedded_in_case_data(client, fake_db):
    login_as(ORG_A)
    case_id = client.post("/cases", json={}).json()["case_id"]
    before = copy.deepcopy(fake_db.collections["cases"][case_id]["case_data"])

    response = client.patch(
        f"/cases/{case_id}",
        json={
            "case_data": {
                **before,
                "settings": {"intermediary": {"name": "試験　太郎"}},
            },
        },
    )

    assert response.status_code == 400
    assert fake_db.collections["cases"][case_id]["case_data"] == before


def test_me_returns_org_and_role(client, fake_db):
    login_as(ORG_A_ADMIN)

    response = client.get("/me")

    assert response.status_code == 200
    assert response.json() == {
        "uid": "admin_a",
        "email": "admin@example.com",
        "org_id": "org_a",
        "role": "admin",
    }


def test_member_cannot_update_org_settings(client, fake_db):
    login_as(ORG_A)

    response = client.patch("/org-settings", json={})

    assert response.status_code == 403
    assert fake_db.collections["org_settings"] == {}


def test_admin_updates_only_own_org_settings(client, fake_db):
    login_as(ORG_A_ADMIN)
    payload = {
        "intermediary": {
            "name": "組織　花子",
            "postal_code": "6310855",
            "address": "奈良県奈良市宝来4丁目13番7号",
            "organization": "太田行政書士事務所",
            "phone": "0742405620",
        },
        "receiving_method": {"notification_email": "promot1@gold.ocn.ne.jp"},
    }

    response = client.patch("/org-settings", json=payload)

    assert response.status_code == 200
    assert response.json()["can_update"] is True
    assert fake_db.collections["org_settings"]["org_a"]["receiving_method"] == {
        "method": "メール Email",
        "notification_email": "promot1@gold.ocn.ne.jp",
    }

    login_as(ORG_B)
    other_response = client.get("/org-settings")
    assert other_response.status_code == 200
    assert other_response.json()["org_id"] == "org_b"
    assert other_response.json()["intermediary"]["name"] == ""
    assert other_response.json()["can_update"] is False


def test_case_and_application_data_receive_org_settings(client, fake_db):
    login_as(ORG_A_ADMIN)
    settings = {
        "intermediary": {
            "name": "組織　花子",
            "postal_code": "6310855",
            "address": "奈良県奈良市宝来4丁目13番7号",
            "organization": "太田行政書士事務所",
            "phone": "0742405620",
        },
        "receiving_method": {"notification_email": "Notice@Example.COM"},
    }
    assert client.patch("/org-settings", json=settings).status_code == 200
    case_id = client.post("/cases", json={}).json()["case_id"]
    assert client.patch(
        f"/cases/{case_id}", json={"workflow_state": "extracted"}
    ).status_code == 200

    case_payload = client.get(f"/cases/{case_id}").json()
    application_payload = client.get(f"/cases/{case_id}/application-data").json()
    rows = {row["canonical_path"]: row["fill_value"] for row in application_payload["rows"]}

    assert case_payload["case_data"]["settings"]["intermediary"]["name"] == "組織　花子"
    assert rows["settings.receiving_method.method"] == "メール Email"
    assert rows["settings.receiving_method.notification_email"] == "notice@example.com"
    assert rows["settings.receiving_method.notification_email_confirmation"] == "notice@example.com"
    assert application_payload["fillable"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [("postal_code", "631-0855"), ("phone", "0742-40-5620"), ("postal_code", "６３１０８５５")],
)
def test_org_settings_rejects_non_ascii_numeric_contact_fields(client, fake_db, field, value):
    login_as(ORG_A_ADMIN)
    intermediary = {
        "name": "組織　花子",
        "postal_code": "6310855",
        "address": "奈良県奈良市宝来4丁目13番7号",
        "organization": "太田行政書士事務所",
        "phone": "0742405620",
    }
    intermediary[field] = value

    response = client.patch(
        "/org-settings",
        json={
            "intermediary": intermediary,
            "receiving_method": {"notification_email": "promot1@gold.ocn.ne.jp"},
        },
    )

    assert response.status_code == 400


def test_partial_intermediary_env_does_not_break_case_or_application_data(
    client,
    fake_db,
    monkeypatch,
):
    env_names = (
        "INTERMEDIARY_NAME",
        "INTERMEDIARY_POSTAL_CODE",
        "INTERMEDIARY_ADDRESS",
        "INTERMEDIARY_ORGANIZATION",
        "INTERMEDIARY_PHONE",
    )
    for env_name in env_names:
        monkeypatch.delenv(env_name, raising=False)
    private_value = "非公開　試験値"
    monkeypatch.setenv("INTERMEDIARY_NAME", private_value)
    login_as(ORG_A)
    case_id = client.post("/cases", json={}).json()["case_id"]

    case_response = client.get(f"/cases/{case_id}")
    application_response = client.get(f"/cases/{case_id}/application-data")

    assert case_response.status_code == 200
    assert private_value not in case_response.text
    assert application_response.status_code == 200
    payload = application_response.json()
    assert payload["fillable"] is False
    assert payload["intermediary_gate"]["status"] == "blocked"
    assert not any(
        row["canonical_path"].startswith("settings.intermediary.")
        for row in payload["rows"]
    )
    assert private_value not in application_response.text


def test_api_without_org_settings_does_not_use_global_intermediary_env(
    client,
    fake_db,
    monkeypatch,
):
    env_values = {
        "INTERMEDIARY_NAME": "環境　太郎",
        "INTERMEDIARY_POSTAL_CODE": "1234567",
        "INTERMEDIARY_ADDRESS": "東京都千代田区霞が関一丁目",
        "INTERMEDIARY_ORGANIZATION": "環境行政書士法人",
        "INTERMEDIARY_PHONE": "0312345678",
    }
    for key, value in env_values.items():
        monkeypatch.setenv(key, value)
    login_as(ORG_A)
    case_id = client.post("/cases", json={}).json()["case_id"]
    assert client.patch(
        f"/cases/{case_id}", json={"workflow_state": "extracted"}
    ).status_code == 200

    case_response = client.get(f"/cases/{case_id}")
    application_response = client.get(f"/cases/{case_id}/application-data")

    assert case_response.status_code == 200
    assert not any(value in case_response.text for value in env_values.values())
    assert application_response.status_code == 200
    payload = application_response.json()
    assert payload["fillable"] is False
    assert payload["settings_gate"]["status"] == "blocked"
    assert not any(
        row["canonical_path"].startswith("settings.intermediary.")
        for row in payload["rows"]
    )
    assert not any(value in application_response.text for value in env_values.values())


def test_strip_api_prefix_still_requires_auth(client, fake_db):
    assert client.get("/api/cases").status_code == 401
