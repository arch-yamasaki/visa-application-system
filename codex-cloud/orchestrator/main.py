"""Codex orchestrator – FastAPI service on Cloud Run."""

import json
import mimetypes
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
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


class CreateCaseRequest(BaseModel):
    application_type: str = "certificate_of_eligibility"
    target_status: str = "engineer_humanities_international"


class UpdateCaseRequest(BaseModel):
    case_data: dict | None = None
    field_metadata: dict | None = None
    workflow_state: str | None = None


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


# ---------------------------------------------------------------------------
# Case Endpoints
# ---------------------------------------------------------------------------
@app.post("/cases")
def create_case(body: CreateCaseRequest):
    case_id = f"case_{uuid.uuid4().hex[:12]}"
    now = _now_iso()

    case_data = {
        "schema_version": "1.0",
        "case": {
            "case_id": case_id,
            "application_type": body.application_type,
            "target_status": body.target_status,
            "workflow_state": "draft",
        },
        "applicant": {},
        "application": {},
    }

    doc = {
        "case_id": case_id,
        "workflow_state": "draft",
        "created_at": now,
        "updated_at": now,
        "case_data": case_data,
        "field_metadata": {},
        "review": {},
        "document_manifest": {"documents": []},
        "extraction_session_id": None,
        "confirmed_at": None,
    }

    db.collection("cases").document(case_id).set(doc)

    return {"case_id": case_id, "workflow_state": "draft", "created_at": now}


@app.get("/cases")
def list_cases(
    limit: int = Query(default=20, ge=1, le=100),
    workflow_state: Optional[str] = Query(default=None),
):
    query = db.collection("cases")
    if workflow_state:
        query = query.where("workflow_state", "==", workflow_state)
    query = query.order_by("created_at", direction=firestore.Query.DESCENDING).limit(
        limit
    )
    return [doc.to_dict() for doc in query.stream()]


@app.get("/cases/{case_id}")
def get_case(case_id: str):
    doc = db.collection("cases").document(case_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Case not found")
    return doc.to_dict()


@app.patch("/cases/{case_id}")
def update_case(case_id: str, body: UpdateCaseRequest):
    ref = db.collection("cases").document(case_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Case not found")

    updates: dict = {"updated_at": _now_iso()}

    if body.case_data is not None:
        updates["case_data"] = body.case_data
    if body.field_metadata is not None:
        updates["field_metadata"] = body.field_metadata
    if body.workflow_state is not None:
        updates["workflow_state"] = body.workflow_state
        if body.workflow_state == "ready_to_fill":
            updates["confirmed_at"] = _now_iso()

    ref.update(updates)

    return ref.get().to_dict()


@app.post("/cases/{case_id}/documents")
async def upload_case_document(
    case_id: str,
    file: UploadFile = File(...),
    document_role: str = Form(default="applicant_document_bundle"),
):
    ref = db.collection("cases").document(case_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Case not found")

    document_id = f"doc_{uuid.uuid4().hex[:8]}"
    original_filename = file.filename or "upload"
    gcs_path = f"cases/{case_id}/documents/{document_id}_{original_filename}"

    bucket = gcs.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_path)

    content = await file.read()
    blob.upload_from_string(
        content,
        content_type=file.content_type or "application/octet-stream",
    )

    doc_entry = {
        "document_id": document_id,
        "file_name": original_filename,
        "gcs_path": gcs_path,
        "document_role": document_role,
        "uploaded_at": _now_iso(),
    }

    ref.update(
        {
            "document_manifest.documents": firestore.ArrayUnion([doc_entry]),
            "updated_at": _now_iso(),
        }
    )

    return {
        "document_id": document_id,
        "file_name": original_filename,
        "gcs_path": gcs_path,
        "document_role": document_role,
    }


@app.get("/cases/{case_id}/documents")
def list_case_documents(case_id: str):
    doc = db.collection("cases").document(case_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Case not found")
    data = doc.to_dict()
    return data.get("document_manifest", {"documents": []})


@app.get("/cases/{case_id}/documents/{document_id}/url")
def get_document_url(case_id: str, document_id: str):
    doc = db.collection("cases").document(case_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Case not found")

    data = doc.to_dict()
    manifest = data.get("document_manifest", {})
    documents = manifest.get("documents", [])

    target_doc = None
    for d in documents:
        if d.get("document_id") == document_id:
            target_doc = d
            break

    if not target_doc:
        raise HTTPException(status_code=404, detail="Document not found in manifest")

    gcs_path = target_doc["gcs_path"]
    bucket = gcs.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_path)

    try:
        signed_url = blob.generate_signed_url(
            expiration=timedelta(minutes=15), method="GET"
        )
        return {
            "signed_url": signed_url,
            "document_id": document_id,
            "file_name": target_doc.get("file_name"),
        }
    except Exception:
        return {
            "signed_url": None,
            "gcs_path": gcs_path,
            "document_id": document_id,
            "file_name": target_doc.get("file_name"),
            "note": "Signed URL generation failed. Use gcs_path to access the file directly.",
        }


@app.post("/cases/{case_id}/extract")
def start_extraction(case_id: str):
    ref = db.collection("cases").document(case_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Case not found")

    data = doc.to_dict()
    manifest = data.get("document_manifest", {})
    documents = manifest.get("documents", [])

    if not documents:
        raise HTTPException(
            status_code=400, detail="No documents uploaded for this case"
        )

    # Build extraction prompt
    doc_list_text = "\n".join(
        f"- {d['file_name']} (role: {d['document_role']}, gcs: gs://{GCS_BUCKET}/{d['gcs_path']})"
        for d in documents
    )
    prompt = (
        f"You are a visa application document extractor.\n"
        f"Case ID: {case_id}\n"
        f"Application type: {data.get('case_data', {}).get('case', {}).get('application_type', 'unknown')}\n"
        f"Target status: {data.get('case_data', {}).get('case', {}).get('target_status', 'unknown')}\n\n"
        f"Documents:\n{doc_list_text}\n\n"
        f"Extract all relevant fields from these documents.\n"
        f"Output the following JSON files in the generated/ directory:\n"
        f"- generated/case_data.json\n"
        f"- generated/review.json\n"
        f"- generated/field_metadata.json\n"
    )

    session_id = _make_session_id()
    run_id = _make_run_id()
    now = _now_iso()

    prompt_gcs_uri = _upload_prompt(session_id, run_id, prompt)
    firestore_doc_path = f"sessions/{session_id}/runs/{run_id}"

    # Write session document
    session_ref = db.collection("sessions").document(session_id)
    run_ref = session_ref.collection("runs").document(run_id)

    session_ref.set(
        {
            "session_id": session_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "latest_run_id": run_id,
            "prompt_preview": prompt[:200],
            "linked_case_id": case_id,
        }
    )

    run_ref.set(
        {
            "run_id": run_id,
            "status": "queued",
            "created_at": now,
            "prompt_gcs_uri": prompt_gcs_uri,
        }
    )

    # Update case with extraction session
    ref.update(
        {
            "extraction_session_id": session_id,
            "workflow_state": "extracting",
            "updated_at": now,
        }
    )

    # Launch the job
    try:
        _launch_job(session_id, run_id, prompt_gcs_uri, firestore_doc_path)
    except Exception as exc:
        run_ref.update({"status": "launch_failed", "error": str(exc)})
        session_ref.update({"status": "launch_failed", "updated_at": _now_iso()})
        ref.update({"workflow_state": "extraction_failed", "updated_at": _now_iso()})
        return {
            "session_id": session_id,
            "status": "launch_failed",
            "error": str(exc),
        }

    return {"session_id": session_id, "status": "running"}


@app.get("/cases/{case_id}/extraction-status")
def get_extraction_status(case_id: str):
    ref = db.collection("cases").document(case_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Case not found")

    data = doc.to_dict()
    session_id = data.get("extraction_session_id")
    if not session_id:
        raise HTTPException(
            status_code=404, detail="No extraction session found for this case"
        )

    # Look up session status
    session_doc = db.collection("sessions").document(session_id).get()
    if not session_doc.exists:
        raise HTTPException(status_code=404, detail="Extraction session not found")

    session_data = session_doc.to_dict()
    status = session_data.get("status", "unknown")

    # If completed and case is still extracting, try to harvest results
    if status == "completed" and data.get("workflow_state") == "extracting":
        latest_run_id = session_data.get("latest_run_id")
        if latest_run_id:
            _harvest_extraction_results(case_id, ref, session_id, latest_run_id)

    return {"status": status, "session_id": session_id}


def _harvest_extraction_results(
    case_id: str,
    case_ref,
    session_id: str,
    run_id: str,
):
    """Extract case_data.json, review.json, field_metadata.json from workspace tarball."""
    blob_path = f"sessions/{session_id}/runs/{run_id}/workspace.tar.zst"
    bucket = gcs.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        return

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = os.path.join(tmp, "workspace.tar.zst")
        blob.download_to_filename(archive_path)
        extract_dir = os.path.join(tmp, "out")
        os.makedirs(extract_dir)
        subprocess.run(
            ["tar", "--zstd", "-xf", archive_path, "-C", extract_dir],
            check=True,
        )

        updates: dict = {"updated_at": _now_iso(), "workflow_state": "needs_review"}

        # Look for generated/ files
        for name, field in [
            ("case_data.json", "case_data"),
            ("review.json", "review"),
            ("field_metadata.json", "field_metadata"),
        ]:
            # Search for the file in the extracted workspace
            matches = list(Path(extract_dir).rglob(f"generated/{name}"))
            if matches:
                try:
                    content = matches[0].read_text(encoding="utf-8")
                    parsed = json.loads(content)
                    updates[field] = parsed
                except (json.JSONDecodeError, OSError):
                    pass

        case_ref.update(updates)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")
