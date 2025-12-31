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
from synthlab.processes._wafer_particles_io import (  # noqa: E402
    find_manifest,
    paths_from_manifest,
)


def _wafer_particles_cfg() -> dict[str, Any]:
    return {
        "n_samples": 3,
        "n_particles": 12,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
        "source": "synthetic",
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
        "io": {"format": "csv"},
        "qc": {
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "bins": {
                "r": {"start": 0.0, "stop": 10.0, "count": 5},
                "theta": {"start": 0.0, "stop": 6.283185307179586, "count": 6},
            },
            "quantiles": [0.5],
            "rules": {},
        },
        "compare_real": {
            "real": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "synthetic": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
                "qc_metrics_path": None,
            },
        },
    }


def _make_cfg(process_name: str, run_name: str, seed: int) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": process_name},
        "wafer_particles": _wafer_particles_cfg(),
    }


def test_compare_real_pipeline(tmp_path: Path) -> None:
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0108_gen", seed=123)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    manifest_path = find_manifest(gen_run)
    assert manifest_path is not None
    particles_path, _samples_path = paths_from_manifest(
        manifest_path,
        expected_schema_version=SCHEMA_VERSION,
        expected_domain=DOMAIN_NAME,
    )

    compare_cfg = _make_cfg("wafer_particles.process.compare_real", "t0108_compare", seed=123)
    compare_cfg["policy"] = {"real_data": {"allow_repo_paths": True}}
    compare_cfg["wafer_particles"]["compare_real"]["real"]["particles_path"] = str(particles_path)
    compare_cfg["wafer_particles"]["compare_real"]["synthetic"]["run_dir"] = str(gen_run)
    compare_run = dispatch_process(cfg=compare_cfg, overrides=[], repo_root=tmp_path)

    real_metrics_path = compare_run / "metrics" / "real_metrics.json"
    diff_path = compare_run / "metrics" / "synth_vs_real_diff.json"
    assert real_metrics_path.exists()
    assert diff_path.exists()

    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    overall = diff["overall"]
    assert overall["hist_r_l1_mean"] <= 1e-8
    assert overall["hist_theta_l1_mean"] <= 1e-8
    summary = diff["summary"]
    assert summary["total_particles_abs"] == 0.0
    assert summary["total_samples_abs"] == 0.0
