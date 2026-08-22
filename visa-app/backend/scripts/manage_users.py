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

    # 組織設定を登録（実行時にFirestoreへ書き込む）
    .venv/bin/python scripts/manage_users.py org-settings set \
        --org chuo-business --name '<取次者氏名>' --postal-code '<半角数字>' \
        --address '奈良県奈良市宝来4丁目13番7号' --organization '<所属機関>' \
        --phone '<半角数字>' --notification-email 'promot1@gold.ocn.ne.jp'
"""

import argparse
import os
import re
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


def set_org_settings(db: firestore.Client, args: argparse.Namespace) -> None:
    notification_email = args.notification_email.strip().lower()
    values = {
        "name": args.name.strip(),
        "postal_code": args.postal_code.strip(),
        "address": args.address.strip(),
        "organization": args.organization.strip(),
        "phone": args.phone.strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if not notification_email:
        missing.append("notification_email")
    if missing:
        raise SystemExit(f"missing org settings: {', '.join(missing)}")
    for field in ("postal_code", "phone"):
        if not re.fullmatch(r"[0-9]+", values[field]):
            raise SystemExit(f"{field} must contain half-width digits only")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", notification_email):
        raise SystemExit("invalid notification_email")

    payload = {
        "org_id": args.org,
        "intermediary": values,
        "receiving_method": {
            "method": "メール Email",
            "notification_email": notification_email,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by_uid": "manage_users.py",
    }
    db.collection("org_settings").document(args.org).set(payload)
    print(f"org_settings set: org={args.org} notification_email={notification_email}")


def list_org_settings(db: firestore.Client, args: argparse.Namespace) -> None:
    if args.org:
        docs = [db.collection("org_settings").document(args.org).get()]
    else:
        docs = list(db.collection("org_settings").stream())
    for doc in docs:
        if not doc.exists:
            continue
        settings = doc.to_dict()
        receiving = settings.get("receiving_method") or {}
        print(
            f"{settings.get('org_id', args.org or '')}  "
            f"organization={settings.get('intermediary', {}).get('organization', '')}  "
            f"notification_email={receiving.get('notification_email', '')}"
        )


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

    org_settings_parser = subparsers.add_parser("org-settings", help="組織設定を管理する")
    org_settings_commands = org_settings_parser.add_subparsers(dest="org_settings_command", required=True)

    org_settings_set = org_settings_commands.add_parser("set", help="組織設定を登録・更新する")
    org_settings_set.add_argument("--org", required=True)
    org_settings_set.add_argument("--name", required=True, help="取次者氏名")
    org_settings_set.add_argument("--postal-code", required=True, help="半角数字のみ")
    org_settings_set.add_argument("--address", required=True, help="取次者住所")
    org_settings_set.add_argument("--organization", required=True, help="取次者所属機関")
    org_settings_set.add_argument("--phone", required=True, help="半角数字のみ")
    org_settings_set.add_argument(
        "--notification-email",
        required=True,
        help="通知送信用メールアドレス",
    )
    org_settings_set.set_defaults(func=set_org_settings)

    org_settings_list = org_settings_commands.add_parser("list", help="組織設定を一覧する")
    org_settings_list.add_argument("--org")
    org_settings_list.set_defaults(func=list_org_settings)

    args = parser.parse_args()
    firebase_admin.initialize_app(options={"projectId": GCP_PROJECT})
    db = firestore.Client(project=GCP_PROJECT)
    args.func(db, args)


if __name__ == "__main__":
    main()
