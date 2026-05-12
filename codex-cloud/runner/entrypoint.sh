#!/usr/bin/env bash
set -euo pipefail

# ── Required env vars ──
: "${SESSION_ID:?SESSION_ID is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${PROMPT_GCS_URI:?PROMPT_GCS_URI is required}"
: "${GCS_BUCKET:?GCS_BUCKET is required}"
: "${FIRESTORE_DOC_PATH:?FIRESTORE_DOC_PATH is required}"

# ── Auth: subscription (auth.json) or API key ──
CODEX_HOME="${CODEX_HOME:-/codex-state/home}"
export CODEX_HOME
mkdir -p "$CODEX_HOME"

if [ -f "/var/run/secrets/codex-auth/auth.json" ]; then
  echo "Using subscription auth (auth.json)"
  cp /var/run/secrets/codex-auth/auth.json "$CODEX_HOME/auth.json"
elif [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "Using API key auth"
  export CODEX_API_KEY="$OPENAI_API_KEY"
else
  echo "ERROR: No auth method available (need auth.json or OPENAI_API_KEY)" >&2
  exit 1
fi

WORKSPACE_DIR="/workspace/current"
OUTPUT_DIR="/workspace/out"
GCS_PREFIX="gs://${GCS_BUCKET}/sessions/${SESSION_ID}/runs/${RUN_ID}"

mkdir -p "$WORKSPACE_DIR" "$OUTPUT_DIR"

# ── Init workspace as git repo (codex requires it) ──
if [ ! -d "$WORKSPACE_DIR/.git" ]; then
  git init "$WORKSPACE_DIR" --quiet
  git -C "$WORKSPACE_DIR" -c user.name="codex-runner" -c user.email="codex@runner" commit --allow-empty -m "init" --quiet
fi

# ── Cleanup trap ──
cleanup() {
  local exit_code=$?
  # Always clean up auth
  rm -f "$CODEX_HOME/auth.json"
  if [ $exit_code -ne 0 ]; then
    echo "Job failed with exit code $exit_code"
    if [ -f "$OUTPUT_DIR/stderr.txt" ]; then
      python3 /app/gcs_helper.py upload "$OUTPUT_DIR/stderr.txt" "${GCS_PREFIX}/stderr.txt" || true
    fi
    python3 /app/update_status.py "$FIRESTORE_DOC_PATH" "failed" \
      --exit-code "$exit_code" \
      --stderr-uri "${GCS_PREFIX}/stderr.txt" || true
  fi
}
trap cleanup EXIT

# ── 1. Set status to running ──
echo "Setting status to running..."
python3 /app/update_status.py "$FIRESTORE_DOC_PATH" "running"

# ── 2. Download prompt from GCS ──
echo "Downloading prompt from ${PROMPT_GCS_URI}..."
python3 /app/gcs_helper.py download "$PROMPT_GCS_URI" /tmp/prompt.txt
PROMPT=$(cat /tmp/prompt.txt)

# ── 3. Optionally restore workspace ──
if [ -n "${WORKSPACE_INPUT_GCS_URI:-}" ]; then
  echo "Restoring workspace from ${WORKSPACE_INPUT_GCS_URI}..."
  python3 /app/gcs_helper.py download "$WORKSPACE_INPUT_GCS_URI" /tmp/workspace.tar.zst
  tar --zstd -xf /tmp/workspace.tar.zst -C "$WORKSPACE_DIR"
fi

# ── 4. Run codex ──
CODEX_TIMEOUT="${CODEX_TIMEOUT:-1200}"  # default 20 minutes
echo "Running codex exec (timeout: ${CODEX_TIMEOUT}s)..."
CODEX_EXIT=0
timeout "$CODEX_TIMEOUT" \
  codex exec --json \
  --sandbox workspace-write \
  --skip-git-repo-check \
  --output-last-message "$OUTPUT_DIR/last_message.txt" \
  -C "$WORKSPACE_DIR" \
  -- "$PROMPT" \
  > "$OUTPUT_DIR/stdout.jsonl" \
  2> "$OUTPUT_DIR/stderr.txt" \
  || CODEX_EXIT=$?

# ── 5. Create workspace tarball ──
echo "Creating workspace tarball..."
tar --zstd -cf "$OUTPUT_DIR/workspace.tar.zst" -C "$WORKSPACE_DIR" .

# ── 6. Upload outputs to GCS ──
echo "Uploading outputs..."
python3 /app/gcs_helper.py upload "$OUTPUT_DIR/stdout.jsonl" "${GCS_PREFIX}/stdout.jsonl"
python3 /app/gcs_helper.py upload "$OUTPUT_DIR/stderr.txt" "${GCS_PREFIX}/stderr.txt"
python3 /app/gcs_helper.py upload "$OUTPUT_DIR/workspace.tar.zst" "${GCS_PREFIX}/workspace.tar.zst"

LAST_MSG_URI=""
if [ -f "$OUTPUT_DIR/last_message.txt" ]; then
  python3 /app/gcs_helper.py upload "$OUTPUT_DIR/last_message.txt" "${GCS_PREFIX}/last_message.txt"
  LAST_MSG_URI="${GCS_PREFIX}/last_message.txt"
fi

# ── 7. Update Firestore to completed ──
echo "Updating status to completed..."
python3 /app/update_status.py "$FIRESTORE_DOC_PATH" "completed" \
  --exit-code "$CODEX_EXIT" \
  --stdout-uri "${GCS_PREFIX}/stdout.jsonl" \
  --stderr-uri "${GCS_PREFIX}/stderr.txt" \
  ${LAST_MSG_URI:+--last-message-uri "$LAST_MSG_URI"}

# ── 8. Clean up auth before exit ──
rm -f "$CODEX_HOME/auth.json"

# Disable trap since we succeeded
trap - EXIT
echo "Done."
