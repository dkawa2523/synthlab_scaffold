from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402


def _wafer_particles_cfg(radius_mm: float, width_mm: float) -> dict[str, Any]:
    return {
        "n_samples": 6,
        "n_particles": 180,
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
            }
        },
        "size_models": {
            "name": "wafer_particles.size_model.lognormal",
            "mu_log": 0.0,
            "sigma_log": 0.1,
        },
        "io": {"format": "csv"},
    }


def _calibrate_cfg(real_run: Path) -> dict[str, Any]:
    return {
        "real": {
            "run_dir": str(real_run),
        },
        "search": {
            "algorithm": "random",
            "n_trials": 6,
            "seed_offset": 0,
            "include_baseline": True,
            "warm_start": [
                {
                    "patterns.ring_narrow.radius_mm": 6.0,
                    "patterns.ring_narrow.width_mm": 1.2,
                }
            ],
            "params": [
                {
                    "name": "radius_mm",
                    "path": "patterns.ring_narrow.radius_mm",
                    "min": 4.0,
                    "max": 7.0,
                },
                {
                    "name": "width_mm",
                    "path": "patterns.ring_narrow.width_mm",
                    "min": 0.6,
                    "max": 1.5,
                },
            ],
        },
        "bins": {
            "r": {"start": 0.0, "stop": 10.0, "count": 10},
            "theta": {"start": 0.0, "stop": 6.283185307179586, "count": 12},
            "size": {"start": 0.0, "stop": 5.0, "count": 10},
        },
        "score": {
            "weights": {
                "hist_r_l1": 1.0,
                "hist_theta_l1": 1.0,
                "hist_size_l1": 1.0,
                "nn_distance_ks": 0.0,
            }
        },
        "spatial": {
            "enable_nn": False,
            "nn_max_points": None,
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


def test_T0402_calibrate_search_improves_and_reproducible(tmp_path: Path) -> None:
    real_cfg = _make_cfg(
        "wafer_particles.process.generate",
        "t0402_real",
        seed=11,
        wp_cfg=_wafer_particles_cfg(radius_mm=6.0, width_mm=1.2),
    )
    real_run = dispatch_process(cfg=real_cfg, overrides=[], repo_root=tmp_path)

    calib_wp_cfg = _wafer_particles_cfg(radius_mm=4.5, width_mm=0.6)
    calib_wp_cfg["calibrate_search"] = _calibrate_cfg(real_run)
    calib_cfg = _make_cfg(
        "wafer_particles.process.calibrate_search",
        "t0402_calibrate",
        seed=21,
        wp_cfg=calib_wp_cfg,
    )
    run_a = dispatch_process(cfg=calib_cfg, overrides=[], repo_root=tmp_path)

    calib_cfg["run_name"] = "t0402_calibrate_repeat"
    run_b = dispatch_process(cfg=calib_cfg, overrides=[], repo_root=tmp_path)

    best_path = run_a / "metrics" / "best_score.json"
    trials_path = run_a / "metrics" / "trials.csv"
    config_path = run_a / "config" / "best_config.yaml"
    assert best_path.exists()
    assert trials_path.exists()
    assert config_path.exists()

    best_a = json.loads(best_path.read_text(encoding="utf-8"))
    best_b = json.loads((run_b / "metrics" / "best_score.json").read_text(encoding="utf-8"))
    assert best_a["best"]["score"] == best_b["best"]["score"]
    assert best_a["best"]["params"] == best_b["best"]["params"]

    baseline = best_a.get("baseline")
    assert baseline is not None
    assert best_a["best"]["score"] < baseline["score"]

    best_cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    params = best_cfg["wafer_particles"]["patterns"]["ring_narrow"]
    assert abs(params["radius_mm"] - 6.0) <= 0.6
    assert abs(params["width_mm"] - 1.2) <= 0.6
