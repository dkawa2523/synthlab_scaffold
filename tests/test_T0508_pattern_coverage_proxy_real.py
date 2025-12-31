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


def _wafer_particles_cfg(radius_mm: float, width_mm: float) -> dict[str, Any]:
    return {
        "n_samples": 4,
        "n_particles": 120,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
        "source": "synthetic",
        "label_selection": {
            "mode": "fixed",
            "labels": ["ring_narrow"],
            "shuffle": False,
        },
        "patterns": {
            "ring_narrow": {
                "name": "wafer_particles.pattern.ring_narrow",
                "radius_mm": radius_mm,
                "width_mm": width_mm,
                "param_space": {
                    "radius_mm": {"dist": "uniform", "min": radius_mm, "max": radius_mm},
                    "width_mm": {"dist": "uniform", "min": width_mm, "max": width_mm},
                },
            },
            "random_uniform": {
                "name": "wafer_particles.pattern.random_uniform",
            },
            "scratch": {
                "name": "wafer_particles.pattern.scratch",
                "width_ratio": 0.02,
                "length_ratio": 1.0,
            },
        },
        "size_models": {
            "name": "wafer_particles.size_model.lognormal",
            "mu_log": 0.0,
            "sigma_log": 0.1,
        },
        "io": {"format": "csv"},
    }


def _coverage_cfg(real_run: Path) -> dict[str, Any]:
    return {
        "real_input": {
            "run_dir": str(real_run),
        },
        "pattern_set": ["ring_narrow", "random_uniform", "scratch"],
        "search_budget": 4,
        "allow_composite_search": False,
        "composite_k": 2,
        "threshold_new_pattern": 1.0,
        "bins": {
            "r": {"start": 0.0, "stop": 10.0, "count": 10},
            "theta": {"start": 0.0, "stop": 6.283185307179586, "count": 12},
            "size": {"start": 0.0, "stop": 5.0, "count": 10},
        },
        "score": {
            "weights": {
                "hist_r_l1": 1.0,
                "hist_theta_l1": 1.0,
                "hist_size_l1": 0.5,
                "density_l1": 0.0,
            }
        },
    }


def _make_cfg(process_name: str, run_name: str, seed: int, wp_cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": process_name},
        "wafer_particles": wp_cfg,
        "policy": {"real_data": {"allow_repo_paths": True}},
    }


def test_T0508_pattern_coverage_proxy_real(tmp_path: Path) -> None:
    real_cfg = _make_cfg(
        "wafer_particles.process.generate",
        "t0508_real",
        seed=7,
        wp_cfg=_wafer_particles_cfg(radius_mm=6.0, width_mm=1.2),
    )
    real_run = dispatch_process(cfg=real_cfg, overrides=[], repo_root=tmp_path)

    coverage_cfg = _make_cfg(
        "wafer_particles.process.pattern_coverage",
        "t0508_coverage",
        seed=11,
        wp_cfg=_wafer_particles_cfg(radius_mm=6.0, width_mm=1.2),
    )
    coverage_cfg["coverage"] = _coverage_cfg(real_run)
    run_a = dispatch_process(cfg=coverage_cfg, overrides=[], repo_root=tmp_path)

    coverage_cfg["run_name"] = "t0508_coverage_repeat"
    run_b = dispatch_process(cfg=coverage_cfg, overrides=[], repo_root=tmp_path)

    summary_a = json.loads((run_a / "reports" / "coverage_summary.json").read_text(encoding="utf-8"))
    summary_b = json.loads((run_b / "reports" / "coverage_summary.json").read_text(encoding="utf-8"))
    best_a = summary_a["results"]["best"]
    best_b = summary_b["results"]["best"]
    assert best_a["score"] == best_b["score"]
    assert best_a["params"] == best_b["params"]

    top_patterns = summary_a["results"]["top_patterns"][:3]
    labels = [row["label"] for row in top_patterns]
    assert "ring_narrow" in labels
