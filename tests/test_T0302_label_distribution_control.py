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
        "n_samples": 100,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
        "source": "synthetic",
        "label_selection": {
            "mode": "ratio",
            "ratios": {"ring_narrow": 0.7, "random_uniform": 0.3},
            "shuffle": True,
        },
        "patterns": {
            "ring_narrow": {
                "name": "wafer_particles.pattern.ring_narrow",
                "n_particles_distribution": {"type": "fixed", "value": 12},
                "param_ranges": {"radius_ratio": [0.6, 0.8]},
            },
            "random_uniform": {
                "name": "wafer_particles.pattern.random_uniform",
                "n_particles_distribution": {"type": "range", "min": 5, "max": 9},
            },
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
            "expectations": {
                "label_ratio_tolerance": 0.03,
                "n_particles_mean_tolerance": 0.2,
            },
            "rules": {},
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


def _run_process(tmp_path: Path, cfg: dict[str, Any]) -> Path:
    return dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)


def _read_samples(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples_path = run_dir / manifest["files"]["samples"]["path"]
    return read_table(samples_path)


def test_T0302_generate_label_ratios_and_ranges(tmp_path: Path) -> None:
    cfg = _make_cfg("wafer_particles.process.generate", "t0302_generate", seed=123)
    run_dir = _run_process(tmp_path, cfg)

    samples = _read_samples(run_dir)
    label_counts = Counter(sample["label"] for sample in samples)
    total = len(samples)
    ratio_ring = label_counts["ring_narrow"] / total
    ratio_random = label_counts["random_uniform"] / total

    assert abs(ratio_ring - 0.7) <= 0.03
    assert abs(ratio_random - 0.3) <= 0.03

    ring_samples = [row for row in samples if row["label"] == "ring_narrow"]
    random_samples = [row for row in samples if row["label"] == "random_uniform"]

    assert ring_samples
    assert random_samples
    assert all(row["n_particles"] == 12 for row in ring_samples)
    assert all(5 <= row["n_particles"] <= 9 for row in random_samples)

    for row in ring_samples[:5]:
        params = json.loads(row["pattern_params"])
        assert "param_ranges" not in params
        assert 0.6 <= params["radius_ratio"] <= 0.8


def test_T0302_qc_checks_expected_distribution(tmp_path: Path) -> None:
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0302_gen_qc", seed=11)
    gen_run = _run_process(tmp_path, gen_cfg)

    qc_cfg = _make_cfg("wafer_particles.process.qc", "t0302_qc", seed=11)
    qc_cfg["wafer_particles"]["qc"]["input"]["run_dir"] = str(gen_run)
    qc_run = _run_process(tmp_path, qc_cfg)

    qc_payload = json.loads((qc_run / "metrics" / "qc.json").read_text(encoding="utf-8"))
    labels = qc_payload["labels"]

    assert labels["ring_narrow"]["label_ratio"]["within_tolerance"] is True
    assert labels["random_uniform"]["label_ratio"]["within_tolerance"] is True
    assert labels["ring_narrow"]["n_particles_check"]["within_tolerance"] is True
    assert labels["random_uniform"]["n_particles_check"]["within_tolerance"] is True
