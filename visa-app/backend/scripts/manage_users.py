"""ユーザー発行・管理CLI。

自由サインアップはさせず、管理者がこのスクリプトでユーザーを発行する。
Firebase Authentication のユーザーと、認可に使う Firestore の users
ドキュメント(auth.py 参照)をセットで管理する。

使い方 (visa-app/backend で実行):

    # メール/パスワードのユーザーを新規発行して登録
    .venv/bin/python scripts/manage_users.py create \
        --email staff@example.com --password '...' --org aicx

    # Googleログイン済みユーザーを登録 (本人が一度ログインを試みた後に実行)
    .venv/bin/python scripts/manage_users.py create \
        --email someone@gmail.com --org aicx

    # 登録済みユーザー一覧
    .venv/bin/python scripts/manage_users.py list

    # 既存の cases / sessions に org_id を付与 (認証導入時の一回だけ)
    .venv/bin/python scripts/manage_users.py backfill --org aicx
"""

import argparse
import os
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import auth as firebase_auth
from google.cloud import firestore

GCP_PROJECT = os.environ.get("GCP_PROJECT", "visa-codex-mvp")


def create(db: firestore.Client, args: argparse.Namespace) -> None:
    try:
        user = firebase_auth.get_user_by_email(args.email)
        print(f"Firebase user already exists: {user.uid}")
        if args.password:
            firebase_auth.update_user(user.uid, password=args.password)
            print("Password updated")
    except firebase_auth.UserNotFoundError:
        # パスワードなしで作成した場合は Googleログイン専用ユーザーになる
        kwargs = {"email": args.email}
        if args.password:
            kwargs["password"] = args.password
        user = firebase_auth.create_user(**kwargs)
        print(f"Firebase user created: {user.uid}")

    db.collection("users").document(user.uid).set(
        {
            "email": args.email,
            "org_id": args.org,
            "role": args.role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    print(f"Registered: {args.email} org={args.org} role={args.role}")


def list_users(db: firestore.Client, args: argparse.Namespace) -> None:
    for doc in db.collection("users").stream():
        user = doc.to_dict()
        print(f"{doc.id}  {user.get('email')}  org={user.get('org_id')}  role={user.get('role')}")


def backfill(db: firestore.Client, args: argparse.Namespace) -> None:
    for name in ("cases", "sessions"):
        count = 0
        for doc in db.collection(name).stream():
            if "org_id" not in doc.to_dict():
                doc.reference.update({"org_id": args.org})
                count += 1
        print(f"{name}: {count} docs backfilled with org_id={args.org}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="ユーザーを発行・登録する")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--password", help="省略時は既存Firebaseユーザーの登録のみ行う")
    create_parser.add_argument("--org", required=True)
    create_parser.add_argument("--role", default="member", choices=["admin", "member"])
    create_parser.set_defaults(func=create)

    list_parser = subparsers.add_parser("list", help="登録済みユーザーを一覧する")
    list_parser.set_defaults(func=list_users)

    backfill_parser = subparsers.add_parser("backfill", help="既存データに org_id を付与する")
    backfill_parser.add_argument("--org", required=True)
    backfill_parser.set_defaults(func=backfill)

    args = parser.parse_args()
    firebase_admin.initialize_app(options={"projectId": GCP_PROJECT})
    db = firestore.Client(project=GCP_PROJECT)
    args.func(db, args)


if __name__ == "__main__":
    main()
