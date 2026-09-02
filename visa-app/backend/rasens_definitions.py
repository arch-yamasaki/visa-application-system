"""Load RASENS mapping and form definition data."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BACKEND_DIR.parents[1] if len(BACKEND_DIR.parents) > 1 else BACKEND_DIR


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_mapping_path() -> Path:
    env_path = os.environ.get("RASENS_MAPPING_PATH")
    if env_path:
        return Path(env_path)
    workspace_path = WORKSPACE_DIR / "rasens-autofill/data/mappings/rasens_offer_mapping_v2.json"
    if workspace_path.exists():
        return workspace_path
    return BACKEND_DIR / "data/mappings/rasens_offer_mapping_v2.json"


def default_form_definitions_path() -> Path | None:
    env_path = os.environ.get("RASENS_FORM_DEFINITIONS_PATH")
    if env_path:
        return Path(env_path)
    workspace_path = WORKSPACE_DIR / "rasens-autofill/data/form_definitions/rasens_offer_fields.json"
    if workspace_path.exists():
        return workspace_path
    backend_path = BACKEND_DIR / "data/form_definitions/rasens_offer_fields.json"
    if backend_path.exists():
        return backend_path
    return None


def load_default_mapping() -> dict[str, Any]:
    return load_json(default_mapping_path())


def load_default_form_definitions() -> dict[str, Any]:
    path = default_form_definitions_path()
    if path is None:
        return {}
    return load_json(path)


def select_option_texts_for_canonical_id(
    canonical_id: str,
    mapping: dict[str, Any] | None = None,
    form_definitions: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    mapping = load_default_mapping() if mapping is None else mapping
    form_definitions = load_default_form_definitions() if form_definitions is None else form_definitions
    mapping_item = next(
        (item for item in mapping.get("mappings", []) if item.get("canonical_id") == canonical_id),
        None,
    )
    if mapping_item is None:
        raise ValueError(f"mapping target not found: {canonical_id}")

    field_id = mapping_item.get("field_id", "")
    field_name = mapping_item.get("field_name", "")
    for field in form_definitions.get("fields", []):
        for control in field.get("controls", []):
            if control.get("field_id") != field_id or control.get("field_name") != field_name:
                continue
            if control.get("input_type") != "select":
                raise ValueError(f"mapping target is not a select: {canonical_id}")
            options = tuple(
                option.get("text", "").strip()
                for option in control.get("options", [])
                if option.get("text", "").strip() and not _is_select_placeholder(option)
            )
            if not options:
                raise ValueError(f"select options not found: {canonical_id}")
            return options

    raise ValueError(f"form definition target not found: {canonical_id}")


def _is_select_placeholder(option: dict[str, Any]) -> bool:
    return option.get("value") == "1" and option.get("text", "").strip() == "選択してください"
