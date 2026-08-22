"""Firebase Authentication による API 認証。

リクエストの Bearer トークン(Firebase ID token)を検証し、Firestore の
``users`` コレクションに登録済みのユーザーだけを通す。ユーザーの発行は
管理者が ``scripts/manage_users.py`` で行う(自由サインアップはさせない)。

``users/{uid}`` ドキュメント:

    email:  ログインメールアドレス(表示用)
    org_id: 所属組織。ケース・セッションはこの org_id 単位で分離する
    role:   "admin" | "member" (`org_settings` の更新はadminのみ)
"""

import os
from dataclasses import dataclass

import firebase_admin
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from google.cloud import firestore

GCP_PROJECT = os.environ.get("GCP_PROJECT", "visa-codex-mvp")

firebase_admin.initialize_app(options={"projectId": GCP_PROJECT})
_db = firestore.Client(project=GCP_PROJECT)
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str
    org_id: str
    role: str


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header required")
    try:
        decoded = firebase_auth.verify_id_token(credentials.credentials)
    except (ValueError, firebase_auth.InvalidIdTokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user_doc = _db.collection("users").document(decoded["uid"]).get()
    if not user_doc.exists:
        raise HTTPException(status_code=403, detail="User not registered")
    user = user_doc.to_dict()
    return AuthUser(
        uid=decoded["uid"],
        email=decoded.get("email", ""),
        org_id=user["org_id"],
        role=user.get("role", "member"),
    )
