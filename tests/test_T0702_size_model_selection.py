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


def test_T0702_size_model_selection_ratio_and_metadata(tmp_path: Path) -> None:
    cfg = _make_cfg("t0702_size_model_selection", seed=42)
    run_dir = dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)

    samples = _read_samples(run_dir)
    assert samples
    assert all("size_model" in row for row in samples)
    assert all("size_params_json" in row for row in samples)

    model_counts = Counter(row["size_model"] for row in samples)
    assert model_counts["gaussian"] == 5
    assert model_counts["lognormal"] == 5
    assert len(model_counts) == 2

    for row in samples:
        params = json.loads(row["size_params_json"])
        assert abs(float(params["min_um"]) - 0.01) < 1e-9
        assert abs(float(params["max_um"]) - 1.0) < 1e-9
        assert params["per_sample"] is False
        if row["size_model"] == "gaussian":
            assert abs(float(params["mean_um"]) - 0.4) < 1e-9
            assert abs(float(params["std_um"]) - 0.1) < 1e-9
        elif row["size_model"] == "lognormal":
            assert abs(float(params["mu_log"]) - -0.2) < 1e-9
            assert abs(float(params["sigma_log"]) - 0.2) < 1e-9
        else:
            raise AssertionError(f"unexpected size_model: {row['size_model']}")


def test_T0702_size_model_selection_is_deterministic(tmp_path: Path) -> None:
    cfg_a = _make_cfg("t0702_size_model_selection_a", seed=7)
    cfg_b = _make_cfg("t0702_size_model_selection_b", seed=7)
    run_a = dispatch_process(cfg=cfg_a, overrides=[], repo_root=tmp_path)
    run_b = dispatch_process(cfg=cfg_b, overrides=[], repo_root=tmp_path)

    samples_a = _read_samples(run_a)
    samples_b = _read_samples(run_b)
    models_a = [row["size_model"] for row in samples_a]
    models_b = [row["size_model"] for row in samples_b]
    assert models_a == models_b
