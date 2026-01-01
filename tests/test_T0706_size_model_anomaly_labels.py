from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import find_manifest, read_table  # noqa: E402


def _wafer_particles_cfg() -> dict[str, Any]:
    return {
        "n_samples": 10,
        "n_particles": 5,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
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
            "min_um": 0.01,
            "max_um": 1.0,
            "selection": {
                "mode": "ratio",
                "shuffle": True,
                "ratios": {"gaussian": 1.0, "lognormal": 1.0},
                "anomaly_types": ["lognormal"],
                "anomaly_label_name": "is_size_anomaly",
            },
            "models": {
                "gaussian": {
                    "type": "gaussian",
                    "mean_um": 0.4,
                    "std_um": 0.1,
                },
                "lognormal": {
                    "type": "lognormal",
                    "mu_log": -0.2,
                    "sigma_log": 0.2,
                },
            },
        },
        "io": {"format": "csv"},
    }


def _make_cfg(run_name: str, seed: int) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": "wafer_particles.process.generate"},
        "wafer_particles": _wafer_particles_cfg(),
    }


def _read_samples(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples_path = run_dir / manifest["files"]["samples"]["path"]
    return read_table(samples_path)


def test_T0706_size_model_anomaly_labels(tmp_path: Path) -> None:
    cfg = _make_cfg("t0706_size_model_anomaly_labels", seed=42)
    run_dir = dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)

    samples = _read_samples(run_dir)
    assert samples
    assert all("is_size_anomaly" in row for row in samples)
    assert all("size_anomaly_type" in row for row in samples)

    anomaly_flags = [row["is_size_anomaly"] for row in samples]
    assert all(flag in (0, 1) for flag in anomaly_flags)
    assert sum(anomaly_flags) == 5

    for row in samples:
        if row["is_size_anomaly"] == 1:
            assert row["size_anomaly_type"] == "lognormal"
        else:
            assert row["size_anomaly_type"] == "none"


def test_T0706_size_model_anomaly_labels_deterministic(tmp_path: Path) -> None:
    cfg_a = _make_cfg("t0706_size_model_anomaly_labels_a", seed=7)
    cfg_b = _make_cfg("t0706_size_model_anomaly_labels_b", seed=7)
    run_a = dispatch_process(cfg=cfg_a, overrides=[], repo_root=tmp_path)
    run_b = dispatch_process(cfg=cfg_b, overrides=[], repo_root=tmp_path)

    samples_a = _read_samples(run_a)
    samples_b = _read_samples(run_b)
    flags_a = [row["is_size_anomaly"] for row in samples_a]
    flags_b = [row["is_size_anomaly"] for row in samples_b]
    types_a = [row["size_anomaly_type"] for row in samples_a]
    types_b = [row["size_anomaly_type"] for row in samples_b]
    assert flags_a == flags_b
    assert types_a == types_b
