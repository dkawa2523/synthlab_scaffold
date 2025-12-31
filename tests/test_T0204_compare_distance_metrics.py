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
    }


def _compare_cfg() -> dict[str, Any]:
    return {
        "process_name": "wafer_particles.process.generate",
        "a_run": None,
        "b_run": None,
        "bins": {
            "r": {"start": 0.0, "stop": 10.0, "count": 5},
            "theta": {"start": 0.0, "stop": 6.283185307179586, "count": 6},
        },
        "smoothing": {"epsilon": 1e-9},
        "spatial": {"nn_max_points": None},
    }


def _make_cfg(process_name: str, run_name: str, seed: int) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": process_name},
        "wafer_particles": _wafer_particles_cfg(),
        "compare": _compare_cfg(),
    }


def test_compare_self_consistency(tmp_path: Path) -> None:
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0204_gen", seed=11)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    compare_cfg = _make_cfg("wafer_particles.process.compare", "t0204_compare", seed=13)
    compare_cfg["compare"]["a_run"] = str(gen_run)
    compare_cfg["compare"]["b_run"] = str(gen_run)
    compare_run = dispatch_process(cfg=compare_cfg, overrides=[], repo_root=tmp_path)

    summary_path = compare_run / "metrics" / "compare_summary.json"
    table_path = compare_run / "metrics" / "compare_table.csv"
    assert summary_path.exists()
    assert table_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "r_hist_js" in summary
    assert "theta_hist_js" in summary
    assert "size_ks" in summary
    assert "size_wasserstein" in summary

    assert summary["r_hist_js"] <= 1e-8
    assert summary["theta_hist_js"] <= 1e-8
    assert summary["size_ks"] <= 1e-8
    assert summary["size_wasserstein"] <= 1e-8
    assert summary["nn_distance_ks"] <= 1e-8
