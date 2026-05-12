"""Update Firestore document status for a Codex run."""

import argparse
import sys
from datetime import datetime, timezone

from google.cloud import firestore


def update_status(
    doc_path: str,
    status: str,
    *,
    last_message_uri: str | None = None,
    stdout_uri: str | None = None,
    stderr_uri: str | None = None,
    exit_code: int | None = None,
) -> None:
    db = firestore.Client()

    parts = doc_path.split("/")
    if len(parts) < 2 or len(parts) % 2 != 0:
        raise ValueError(f"Invalid Firestore doc path: {doc_path}")

    doc_ref = db.document(doc_path)

    data: dict = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if status == "running":
        data["started_at"] = datetime.now(timezone.utc)
    if last_message_uri is not None:
        data["last_message_uri"] = last_message_uri
    if stdout_uri is not None:
        data["stdout_uri"] = stdout_uri
    if stderr_uri is not None:
        data["stderr_uri"] = stderr_uri
    if exit_code is not None:
        data["exit_code"] = exit_code

    doc_ref.set(data, merge=True)
    print(f"Firestore {doc_path} -> status={status}")

    # Also update the parent session doc status so the frontend can poll it
    if "/runs/" in doc_path:
        session_path = doc_path.split("/runs/")[0]
        session_ref = db.document(session_path)
        session_ref.set(
            {"status": status, "updated_at": datetime.now(timezone.utc)},
            merge=True,
        )
        print(f"Firestore {session_path} -> status={status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update Firestore run status")
    parser.add_argument("doc_path", help="Firestore document path (e.g. sessions/s1/runs/r1)")
    parser.add_argument("status", help="Status value (e.g. running, completed, failed)")
    parser.add_argument("--last-message-uri", default=None)
    parser.add_argument("--stdout-uri", default=None)
    parser.add_argument("--stderr-uri", default=None)
    parser.add_argument("--exit-code", type=int, default=None)
    args = parser.parse_args()

    try:
        update_status(
            args.doc_path,
            args.status,
            last_message_uri=args.last_message_uri,
            stdout_uri=args.stdout_uri,
            stderr_uri=args.stderr_uri,
            exit_code=args.exit_code,
        )
    except Exception as e:
        print(f"Error updating Firestore: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
