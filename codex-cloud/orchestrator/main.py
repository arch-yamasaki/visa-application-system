"""Codex orchestrator – FastAPI service on Cloud Run."""

import mimetypes
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from google.cloud import firestore, storage
from google.cloud import run_v2
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GCS_BUCKET = os.environ.get("GCS_BUCKET", "visa-codex-mvp-data")
GCP_PROJECT = os.environ.get("GCP_PROJECT", "visa-codex-mvp")
GCP_REGION = os.environ.get("GCP_REGION", "asia-northeast1")
CLOUD_RUN_JOB_NAME = os.environ.get("CLOUD_RUN_JOB_NAME", "codex-runner-job")

# ---------------------------------------------------------------------------
# Clients (initialized lazily on first request via module-level singletons)
# ---------------------------------------------------------------------------
db = firestore.Client(project=GCP_PROJECT)
gcs = storage.Client(project=GCP_PROJECT)
jobs_client = run_v2.JobsClient()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="codex-orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class PromptRequest(BaseModel):
    prompt: str

    @property
    def prompt_stripped(self) -> str:
        return self.prompt.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


def _make_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:4]
    return f"run_{ts}_{suffix}"


def _job_full_name() -> str:
    return f"projects/{GCP_PROJECT}/locations/{GCP_REGION}/jobs/{CLOUD_RUN_JOB_NAME}"


def _upload_prompt(session_id: str, run_id: str, prompt: str) -> str:
    """Upload prompt text to GCS and return the gs:// URI."""
    blob_path = f"sessions/{session_id}/runs/{run_id}/prompt.txt"
    bucket = gcs.bucket(GCS_BUCKET)
    bucket.blob(blob_path).upload_from_string(prompt, content_type="text/plain")
    return f"gs://{GCS_BUCKET}/{blob_path}"


def _launch_job(session_id: str, run_id: str, prompt_gcs_uri: str, firestore_doc_path: str):
    """Launch the Cloud Run Job with execution overrides."""
    overrides = run_v2.types.RunJobRequest.Overrides(
        container_overrides=[
            run_v2.types.RunJobRequest.Overrides.ContainerOverride(
                env=[
                    run_v2.types.EnvVar(name="SESSION_ID", value=session_id),
                    run_v2.types.EnvVar(name="RUN_ID", value=run_id),
                    run_v2.types.EnvVar(name="PROMPT_GCS_URI", value=prompt_gcs_uri),
                    run_v2.types.EnvVar(name="GCS_BUCKET", value=GCS_BUCKET),
                    run_v2.types.EnvVar(name="FIRESTORE_DOC_PATH", value=firestore_doc_path),
                ],
            )
        ],
    )
    request = run_v2.RunJobRequest(name=_job_full_name(), overrides=overrides)
    # Fire-and-forget: the LRO will complete asynchronously.
    jobs_client.run_job(request=request)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/sessions")
def create_session(body: PromptRequest):
    if not body.prompt_stripped:
        raise HTTPException(status_code=400, detail="Prompt must not be empty")

    session_id = _make_session_id()
    run_id = _make_run_id()
    now = _now_iso()

    # Upload prompt to GCS
    prompt_gcs_uri = _upload_prompt(session_id, run_id, body.prompt_stripped)

    # Firestore doc paths
    session_ref = db.collection("sessions").document(session_id)
    run_ref = session_ref.collection("runs").document(run_id)
    firestore_doc_path = f"sessions/{session_id}/runs/{run_id}"

    # Write session document
    session_ref.set(
        {
            "session_id": session_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "latest_run_id": run_id,
            "prompt_preview": body.prompt_stripped[:200],
        }
    )

    # Write run document
    run_ref.set(
        {
            "run_id": run_id,
            "status": "queued",
            "created_at": now,
            "prompt_gcs_uri": prompt_gcs_uri,
        }
    )

    # Launch Cloud Run Job
    try:
        _launch_job(session_id, run_id, prompt_gcs_uri, firestore_doc_path)
    except Exception as exc:
        # Update status but still return the session so the user can inspect
        run_ref.update({"status": "launch_failed", "error": str(exc)})
        session_ref.update({"status": "launch_failed", "updated_at": _now_iso()})
        return {
            "session_id": session_id,
            "run_id": run_id,
            "status": "launch_failed",
            "error": str(exc),
        }

    return {"session_id": session_id, "run_id": run_id, "status": "running"}


@app.get("/sessions")
def list_sessions():
    query = (
        db.collection("sessions")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(20)
    )
    return [doc.to_dict() for doc in query.stream()]


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    session_doc = db.collection("sessions").document(session_id).get()
    if not session_doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    data = session_doc.to_dict()

    # Attach latest run status
    latest_run_id = data.get("latest_run_id")
    if latest_run_id:
        run_doc = (
            db.collection("sessions")
            .document(session_id)
            .collection("runs")
            .document(latest_run_id)
            .get()
        )
        if run_doc.exists:
            data["latest_run"] = run_doc.to_dict()

    return data


@app.get("/sessions/{session_id}/result")
def get_result(session_id: str):
    session_doc = db.collection("sessions").document(session_id).get()
    if not session_doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    data = session_doc.to_dict()
    latest_run_id = data.get("latest_run_id")
    if not latest_run_id:
        raise HTTPException(status_code=404, detail="No run found")

    # Try to download last_message from GCS
    blob_path = f"sessions/{session_id}/runs/{latest_run_id}/last_message.txt"
    bucket = gcs.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        raise HTTPException(status_code=404, detail="Result not available yet")

    content = blob.download_as_text()
    return {"session_id": session_id, "run_id": latest_run_id, "result": content}


@app.get("/sessions/{session_id}/files")
def list_files(session_id: str):
    """List files in the workspace tarball for the latest run."""
    session_doc = db.collection("sessions").document(session_id).get()
    if not session_doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    data = session_doc.to_dict()
    latest_run_id = data.get("latest_run_id")
    if not latest_run_id:
        raise HTTPException(status_code=404, detail="No run found")

    blob_path = f"sessions/{session_id}/runs/{latest_run_id}/workspace.tar.zst"
    bucket = gcs.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        raise HTTPException(status_code=404, detail="Workspace archive not found")

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = os.path.join(tmp, "workspace.tar.zst")
        blob.download_to_filename(archive_path)
        extract_dir = os.path.join(tmp, "out")
        os.makedirs(extract_dir)
        subprocess.run(
            ["tar", "--zstd", "-xf", archive_path, "-C", extract_dir],
            check=True,
        )

        files = []
        for p in Path(extract_dir).rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(extract_dir))
                if not rel.startswith(".git/") and not rel.startswith(".git\\"):
                    files.append(rel)

    files.sort()
    return {"files": files}


@app.get("/sessions/{session_id}/files/{file_path:path}")
def download_file(session_id: str, file_path: str):
    """Download a specific file from the workspace tarball."""
    session_doc = db.collection("sessions").document(session_id).get()
    if not session_doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    data = session_doc.to_dict()
    latest_run_id = data.get("latest_run_id")
    if not latest_run_id:
        raise HTTPException(status_code=404, detail="No run found")

    blob_path = f"sessions/{session_id}/runs/{latest_run_id}/workspace.tar.zst"
    bucket = gcs.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        raise HTTPException(status_code=404, detail="Workspace archive not found")

    # Extract to a temp dir that persists until response is sent
    tmp_dir = tempfile.mkdtemp()
    archive_path = os.path.join(tmp_dir, "workspace.tar.zst")
    blob.download_to_filename(archive_path)
    extract_dir = os.path.join(tmp_dir, "out")
    os.makedirs(extract_dir)
    subprocess.run(
        ["tar", "--zstd", "-xf", archive_path, "-C", extract_dir],
        check=True,
    )

    target = Path(extract_dir) / file_path
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in workspace")

    media_type, _ = mimetypes.guess_type(str(target))
    filename = Path(file_path).name
    return FileResponse(
        path=str(target),
        media_type=media_type or "application/octet-stream",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")
