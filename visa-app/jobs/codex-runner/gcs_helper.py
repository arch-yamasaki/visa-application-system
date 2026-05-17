"""GCS download/upload helper for the Codex runner."""

import sys

from google.cloud import storage


def _parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """Parse gs://bucket/path into (bucket, blob_path)."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    without_scheme = gcs_uri[len("gs://"):]
    bucket, _, blob_path = without_scheme.partition("/")
    if not bucket or not blob_path:
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    return bucket, blob_path


def download(gcs_uri: str, local_path: str) -> None:
    bucket_name, blob_path = _parse_gcs_uri(gcs_uri)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)
    print(f"Downloaded {gcs_uri} -> {local_path}")


def upload(local_path: str, gcs_uri: str) -> None:
    bucket_name, blob_path = _parse_gcs_uri(gcs_uri)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(local_path)
    print(f"Uploaded {local_path} -> {gcs_uri}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: gcs_helper.py <download|upload> <args...>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "download" and len(sys.argv) == 4:
        download(sys.argv[2], sys.argv[3])
    elif command == "upload" and len(sys.argv) == 4:
        upload(sys.argv[2], sys.argv[3])
    else:
        print(f"Usage: gcs_helper.py download <gcs_uri> <local_path>", file=sys.stderr)
        print(f"       gcs_helper.py upload <local_path> <gcs_uri>", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
