# Pre-installed Python Libraries

## Why pre-install?

The Codex runner uses `--sandbox workspace-write`, which restricts filesystem writes to the workspace directory. This means **`pip install` at runtime will fail** because pip needs to write to `/usr/lib/python3/...` (system site-packages). Pre-installing libraries in the Docker image is the only reliable way to make them available without switching to `--sandbox danger-full-access`.

## What's installed

| Category | Libraries | Typical use case |
|---|---|---|
| GCP integration | `google-cloud-storage`, `google-cloud-firestore` | Upload outputs, update job status |
| Document generation | `python-pptx`, `python-docx`, `openpyxl`, `reportlab`, `fpdf2` | Create PPTX/DOCX/XLSX/PDF files |
| PDF reading | `PyPDF2`, `pdfplumber` | Extract text/tables from uploaded PDFs |
| Data processing | `pandas`, `numpy` | CSV/Excel analysis, data transformation |
| Image | `Pillow` | Resize, crop, convert images; also a dep for matplotlib/reportlab |
| Charts | `matplotlib` | Generate charts and plots |
| Templating | `jinja2`, `pyyaml` | Template-driven document generation |
| Web/API | `requests`, `httpx` | Fetch external data (if network is allowed) |

## Image size impact

Estimated additions:
- numpy + pandas: ~80 MB
- matplotlib: ~50 MB
- Pillow: ~15 MB
- reportlab: ~20 MB
- Everything else: ~30 MB combined

**Total increase: ~200 MB** on top of the ~1.2 GB base image. Acceptable for a Cloud Run Jobs container that is pulled once and cached.

## What's NOT included (and why)

- **scipy, scikit-learn, tensorflow, torch** -- heavy ML libraries; unlikely to be needed for document generation tasks. If needed, switch to a larger base image or use `danger-full-access` sandbox.
- **beautifulsoup4, lxml** -- HTML scraping; add if a use case emerges.
- **camelot-py, tabula-py** -- PDF table extraction with Java dependency; pdfplumber covers this without JVM.

## Runtime pip access

Under `--sandbox workspace-write`, Codex **cannot** run `pip install` because site-packages is outside the workspace. Two options if a task needs a library not listed here:

1. **Preferred**: Add the library to `requirements.txt` and rebuild the image. This keeps the sandbox secure.
2. **Escape hatch**: Run the job with `--sandbox danger-full-access`. This allows pip but also allows arbitrary filesystem/network access. Use only for trusted prompts.

Codex can still create and use a **virtualenv inside the workspace** (`python3 -m venv /app/workspace/.venv && .venv/bin/pip install foo`), but this requires downloading packages at runtime, which is slow and requires network access.
