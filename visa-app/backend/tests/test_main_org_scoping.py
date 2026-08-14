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
        self.collections: dict[str, dict] = {"cases": {}, "sessions": {}}

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


def test_strip_api_prefix_still_requires_auth(client, fake_db):
    assert client.get("/api/cases").status_code == 401
