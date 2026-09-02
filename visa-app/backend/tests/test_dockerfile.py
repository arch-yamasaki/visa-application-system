"""Docker packaging checks."""

from pathlib import Path


def test_dockerfile_copies_rasens_definitions_module():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"

    assert "COPY backend/rasens_definitions.py ." in dockerfile.read_text(encoding="utf-8")
