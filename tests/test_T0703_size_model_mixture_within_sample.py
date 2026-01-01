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
        "n_samples": 1,
        "n_particles": 100,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": False,
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
            "type": "mixture",
            "components": [
                {
                    "name": "base",
                    "weight": 0.8,
                    "model": {
                        "type": "gaussian",
                        "mean_um": 1.0,
                        "std_um": 0.0,
                    },
                },
                {
                    "name": "tail",
                    "weight": 0.2,
                    "model": {
                        "type": "gaussian",
                        "mean_um": 10.0,
                        "std_um": 0.0,
                    },
                },
            ],
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


def _read_tables(run_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    particles_path = run_dir / manifest["files"]["particles"]["path"]
    samples_path = run_dir / manifest["files"]["samples"]["path"]
    return read_table(particles_path), read_table(samples_path)


def test_T0703_mixture_records_metadata_and_sizes(tmp_path: Path) -> None:
    cfg = _make_cfg("t0703_mixture", seed=12)
    run_dir = dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)

    particles, samples = _read_tables(run_dir)
    assert samples
    assert all(row.get("size_model") == "mixture" for row in samples)
    assert all("size_params_json" in row for row in samples)

    for row in samples:
        params = json.loads(row["size_params_json"])
        components = params.get("components")
        assert isinstance(components, list)
        weights = [float(component.get("weight", 0.0)) for component in components]
        assert all(weight > 0 for weight in weights)
        assert abs(sum(weights) - 1.0) < 1e-6
        for component in components:
            assert component.get("model_type") == "gaussian"
            model_params = component.get("params")
            assert isinstance(model_params, dict)
            assert model_params.get("mean_um") in {1.0, 10.0}
            assert model_params.get("std_um") == 0.0

    sizes = {float(particle["size_um"]) for particle in particles}
    assert sizes.issubset({1.0, 10.0})
    assert sizes == {1.0, 10.0}
