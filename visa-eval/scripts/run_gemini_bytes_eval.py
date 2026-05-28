#!/usr/bin/env python3
"""Run Gemini scoped extraction for a local eval fixture without GCS."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "visa-app" / "backend"
INLINE_MIB = 1024 * 1024

sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")

from extractors.document_models import LoadedDocument
from extractors.document_preprocessor import prepare_documents
from extractors.gemini_pipeline import extract_documents


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def fixture_paths(work_dir: Path) -> tuple[Path, Path, Path]:
    if (work_dir / "document_manifest.blind.json").exists():
        return (
            work_dir / "scenario.json",
            work_dir / "document_manifest.blind.json",
            work_dir / "generated",
        )
    return (
        work_dir / "scenario.json",
        work_dir / "input" / "document_manifest.json",
        work_dir / "generated",
    )


def resolve_document_path(work_dir: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path

    root_path = ROOT / path
    if root_path.exists():
        return root_path
    return work_dir / path


def input_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    documents = []
    for index, document in enumerate(manifest.get("documents", []), start=1):
        if not document.get("use_as_input", True):
            continue
        normalized = dict(document)
        normalized.setdefault("document_id", f"doc_{index:03d}")
        normalized.setdefault("file_name", Path(normalized["path"]).name)
        normalized.setdefault("document_role", "")
        documents.append(normalized)
    return documents


def load_documents(work_dir: Path, documents: list[dict[str, Any]]) -> list[LoadedDocument]:
    loaded = []
    for document in documents:
        path = resolve_document_path(work_dir, document["path"])
        loaded.append(
            LoadedDocument(
                document_id=document["document_id"],
                file_name=document["file_name"],
                document_role=document.get("document_role", ""),
                content=path.read_bytes(),
            )
        )
    return loaded


def case_meta(scenario: dict[str, Any], manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "case_id": scenario.get("case_id") or manifest.get("case_id", ""),
        "application_type": scenario.get("application_type")
        or manifest.get("application_type", ""),
        "target_status": scenario.get("target_status")
        or manifest.get("target_status", ""),
    }


def run(args: argparse.Namespace) -> None:
    work_dir = args.fixture_dir.resolve()
    scenario_path, manifest_path, default_output_dir = fixture_paths(work_dir)
    scenario = read_json(scenario_path)
    manifest = read_json(manifest_path)
    documents = input_documents(manifest)
    loaded_documents = load_documents(work_dir, documents)
    prepared = prepare_documents(loaded_documents)
    output_dir = (args.output_dir or default_output_dir).resolve()

    print(
        "loaded documents=%d pdfs=%d text_docs=%d images=%d inline_mib=%.2f"
        % (
            len(loaded_documents),
            len(prepared.pdf_contents),
            len(prepared.text_contents),
            len(prepared.image_entries),
            prepared.total_inline_bytes / INLINE_MIB,
        )
    )
    if args.dry_run:
        print(f"dry run: no Gemini request sent; output_dir={output_dir}")
        return

    max_inline_bytes = args.max_inline_mib * INLINE_MIB
    if prepared.total_inline_bytes > max_inline_bytes:
        raise SystemExit(
            "inline bytes exceed limit: %.2f MiB > %d MiB"
            % (prepared.total_inline_bytes / INLINE_MIB, args.max_inline_mib)
        )

    result = extract_documents(
        case_meta(scenario, manifest),
        documents,
        loaded_documents,
        prepared,
        pattern="auto",
        scoped=True,
        run_id=f"eval_{uuid.uuid4().hex[:12]}",
        case_id=scenario.get("case_id") or manifest.get("case_id", ""),
        attach_bbox_refs=False,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "case_data.json", result.display_case_data)
    write_json(output_dir / "field_metadata.json", result.field_metadata)
    write_json(output_dir / "review.json", result.review)
    print(
        "wrote case_data=%s field_metadata=%s review=%s"
        % (
            output_dir / "case_data.json",
            output_dir / "field_metadata.json",
            output_dir / "review.json",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fixture_dir",
        type=Path,
        help="Path to a test case fixture or blind run directory",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-inline-mib", type=int, default=20)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
