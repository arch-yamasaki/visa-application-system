"""auth.require_user のユニットテスト。"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from firebase_admin import auth as firebase_auth

import auth
from auth import AuthUser, require_user


class FakeDoc:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class FakeUsersDb:
    """users コレクションだけを持つ Firestore の代役。"""

    def __init__(self, users: dict[str, dict]):
        self._users = users

    def collection(self, name):
        assert name == "users"
        return self

    def document(self, uid):
        self._uid = uid
        return self

    def get(self):
        return FakeDoc(self._users.get(self._uid))


def _credentials(token: str = "token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_require_user_rejects_missing_token():
    with pytest.raises(HTTPException) as exc_info:
        require_user(None)
    assert exc_info.value.status_code == 401


def test_require_user_rejects_invalid_token(monkeypatch):
    def raise_invalid(token):
        raise firebase_auth.InvalidIdTokenError("bad token")

    monkeypatch.setattr(firebase_auth, "verify_id_token", raise_invalid)
    with pytest.raises(HTTPException) as exc_info:
        require_user(_credentials())
    assert exc_info.value.status_code == 401


def test_require_user_rejects_unregistered_user(monkeypatch):
    monkeypatch.setattr(firebase_auth, "verify_id_token", lambda token: {"uid": "u1", "email": "a@example.com"})
    monkeypatch.setattr(auth, "_db", FakeUsersDb({}))
    with pytest.raises(HTTPException) as exc_info:
        require_user(_credentials())
    assert exc_info.value.status_code == 403


def test_require_user_returns_registered_user(monkeypatch):
    monkeypatch.setattr(firebase_auth, "verify_id_token", lambda token: {"uid": "u1", "email": "a@example.com"})
    monkeypatch.setattr(auth, "_db", FakeUsersDb({"u1": {"email": "a@example.com", "org_id": "org_a", "role": "admin"}}))

    user = require_user(_credentials())

    assert user == AuthUser(uid="u1", email="a@example.com", org_id="org_a", role="admin")
