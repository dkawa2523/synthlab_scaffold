from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import find_manifest, read_table  # noqa: E402


def _wafer_particles_cfg(write_mode: str) -> dict[str, Any]:
    return {
        "n_samples": 12,
        "n_particles": 8,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
        "source": "synthetic",
        "generate": {"chunk_size": 4},
        "label_selection": {
            "mode": "fixed",
            "labels": ["random_uniform"],
            "shuffle": False,
        },
        "patterns": {
            "random_uniform": {
                "name": "wafer_particles.pattern.random_uniform",
            }
        },
        "size_models": {
            "name": "wafer_particles.size_model.lognormal",
            "mu_log": 0.0,
            "sigma_log": 0.1,
        },
        "io": {
            "format": "csv",
            "write_mode": write_mode,
        },
    }


def _make_cfg(run_name: str, seed: int, write_mode: str) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": "wafer_particles.process.generate"},
        "wafer_particles": _wafer_particles_cfg(write_mode),
    }


def _run_generate(tmp_path: Path, cfg: dict[str, Any]) -> Path:
    return dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)


def test_T0301_streaming_generate_manifest_counts(tmp_path: Path) -> None:
    cfg = _make_cfg("t0301_streaming", seed=123, write_mode="streaming")
    run_dir = _run_generate(tmp_path, cfg)

    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    particles_path = run_dir / manifest["files"]["particles"]["path"]
    samples_path = run_dir / manifest["files"]["samples"]["path"]
    particles = read_table(particles_path)
    samples = read_table(samples_path)

    assert len(samples) == manifest["files"]["samples"]["rows"]
    assert len(particles) == manifest["files"]["particles"]["rows"]

    label_counts = Counter(sample["label"] for sample in samples)
    assert manifest["label_distribution"] == dict(label_counts)


def test_T0301_streaming_reproducible_manifest(tmp_path: Path) -> None:
    cfg_a = _make_cfg("t0301_streaming_a", seed=77, write_mode="streaming")
    cfg_b = _make_cfg("t0301_streaming_b", seed=77, write_mode="streaming")

    run_a = _run_generate(tmp_path, cfg_a)
    run_b = _run_generate(tmp_path, cfg_b)

    manifest_a = json.loads((run_a / "manifest.json").read_text(encoding="utf-8"))
    manifest_b = json.loads((run_b / "manifest.json").read_text(encoding="utf-8"))

    assert manifest_a["label_distribution"] == manifest_b["label_distribution"]
    assert manifest_a["files"]["samples"]["rows"] == manifest_b["files"]["samples"]["rows"]
    assert manifest_a["files"]["particles"]["rows"] == manifest_b["files"]["particles"]["rows"]
