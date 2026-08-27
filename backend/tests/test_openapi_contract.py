from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = ROOT / "docs" / "api" / "openapi.yaml"


def test_openapi_contract_keeps_v1_scope() -> None:
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = spec["paths"]
    spec_text = OPENAPI_PATH.read_text(encoding="utf-8")

    assert "kb_ids" not in spec_text
    assert "/workspaces" not in paths
    assert "/workspaces/current" in paths
    assert "/tasks/{task_id}" in paths
