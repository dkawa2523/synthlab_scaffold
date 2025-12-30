from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.framework.artifacts import ArtifactWriter, compute_config_hash


def test_compute_config_hash_ignores_run_name_and_hydra() -> None:
    cfg1 = {
        "run_name": "run_a",
        "seed": 1,
        "hydra": {"runtime": "x"},
        "domain": {"name": "wafer_particles"},
        "process": {"name": "doctor"},
    }
    cfg2 = {
        "run_name": "run_b",
        "seed": 1,
        "hydra": {"runtime": "y"},
        "domain": {"name": "wafer_particles"},
        "process": {"name": "doctor"},
    }
    assert compute_config_hash(cfg1) == compute_config_hash(cfg2)


def test_artifact_writer_creates_contract_files(tmp_path) -> None:
    cfg = {
        "run_name": "test_run",
        "seed": 1,
        "schema_version": "wafer_particles.v1",
        "domain": {"name": "wafer_particles"},
        "process": {"name": "doctor"},
    }
    writer = ArtifactWriter(repo_root=tmp_path, cfg=cfg, overrides=["process=doctor"])
    writer.prepare()

    run_dir = tmp_path / "runs" / cfg["run_name"] / cfg["process"]["name"]
    resolved = run_dir / "config" / "resolved.yaml"
    overrides = run_dir / "config" / "overrides.txt"
    meta_path = run_dir / "meta" / "meta.json"

    assert resolved.exists()
    assert overrides.exists()
    assert meta_path.exists()

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    resolved_cfg = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    assert meta["config_hash"] == compute_config_hash(resolved_cfg)
