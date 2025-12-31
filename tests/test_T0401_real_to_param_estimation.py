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


def _wafer_particles_cfg() -> dict[str, Any]:
    return {
        "n_samples": 9,
        "n_particles": 200,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
        "source": "synthetic",
        "label_selection": {
            "mode": "fixed",
            "labels": ["ring_narrow", "edge_sector", "hotspot"],
        },
        "patterns": {
            "ring_narrow": {
                "name": "wafer_particles.pattern.ring_narrow",
                "radius_mm": 6.0,
                "width_mm": 1.2,
            },
            "edge_sector": {
                "name": "wafer_particles.pattern.edge_sector",
                "angle_center_deg": 60.0,
                "angle_width_deg": 30.0,
                "edge_width_mm": 2.0,
            },
            "hotspot": {
                "name": "wafer_particles.pattern.hotspot",
                "mode": "center",
                "sigma_mm": 1.0,
            },
        },
        "size_models": {
            "name": "wafer_particles.size_model.lognormal",
            "mu_log": 0.0,
            "sigma_log": 0.1,
        },
        "io": {"format": "csv"},
    }


def _fit_params_cfg(run_dir: Path) -> dict[str, Any]:
    return {
        "input": {
            "run_dir": str(run_dir),
        },
        "group_by_label": True,
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


def _angular_distance(a: float, b: float) -> float:
    from math import tau

    diff = abs((a - b) % tau)
    return min(diff, tau - diff)


def test_T0401_fit_params_estimates_basic_patterns(tmp_path: Path) -> None:
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0401_gen", seed=7)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    fit_cfg = _make_cfg("wafer_particles.process.fit_params", "t0401_fit", seed=11)
    fit_cfg["wafer_particles"] = {
        "fit_params": _fit_params_cfg(gen_run),
    }
    fit_run = dispatch_process(cfg=fit_cfg, overrides=[], repo_root=tmp_path)

    est_path = fit_run / "metrics" / "estimated_params.json"
    assert est_path.exists()
    payload = json.loads(est_path.read_text(encoding="utf-8"))

    labels = payload["labels"]
    ring = labels["ring_narrow"]["estimated_params"]
    sector = labels["edge_sector"]["estimated_params"]
    hotspot = labels["hotspot"]["estimated_params"]

    assert abs(ring["radius_mm"] - 6.0) <= 0.4
    assert abs(ring["width_mm"] - 1.2) <= 0.4

    assert _angular_distance(sector["angle_center_rad"], 1.0471975512) <= 0.25
    assert abs(sector["angle_width_rad"] - 0.5235987756) <= 0.25
    assert abs(sector["edge_width_mm"] - 2.0) <= 0.4

    assert abs(hotspot["center_x_mm"]) <= 0.35
    assert abs(hotspot["center_y_mm"]) <= 0.35
    assert abs(hotspot["sigma_mm"] - 1.0) <= 0.35
