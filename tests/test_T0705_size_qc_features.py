from __future__ import annotations

import csv
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
        "n_samples": 4,
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
            "min_um": 0.05,
            "max_um": 5.0,
            "selection": {
                "mode": "list",
                "models": ["gaussian", "lognormal"],
                "shuffle": False,
            },
            "models": {
                "gaussian": {
                    "type": "gaussian",
                    "mean_um": 1.0,
                    "std_um": 0.1,
                },
                "lognormal": {
                    "type": "lognormal",
                    "mu_log": 0.0,
                    "sigma_log": 0.2,
                },
            },
        },
        "io": {
            "format": "csv",
        },
        "size_qc": {
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "quantiles": [0.05, 0.25, 0.5, 0.75, 0.95],
            "tail_ratio": {"low": 0.5, "high": 0.95},
            "ks": {"enabled": True, "min_count": 2},
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


def test_T0705_size_qc_outputs(tmp_path: Path) -> None:
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0705_gen", seed=7)
    gen_run = _run_process(tmp_path, gen_cfg)

    qc_cfg = _make_cfg("wafer_particles.process.size_qc", "t0705_size_qc", seed=7)
    qc_cfg["wafer_particles"]["size_qc"]["input"]["run_dir"] = str(gen_run)
    qc_run = _run_process(tmp_path, qc_cfg)

    stats_path = qc_run / "reports" / "size_stats.csv"
    mix_path = qc_run / "reports" / "size_model_mix.json"
    assert stats_path.exists()
    assert mix_path.exists()

    with stats_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert len(rows) == 4
        header = reader.fieldnames or []
        for column in [
            "size_mean",
            "size_std",
            "size_median",
            "size_q05",
            "size_q25",
            "size_q75",
            "size_q95",
            "size_skewness",
            "size_kurtosis",
            "size_tail_ratio",
        ]:
            assert column in header

    mix_payload = json.loads(mix_path.read_text(encoding="utf-8"))
    size_models = mix_payload.get("size_models", {})
    assert size_models.get("gaussian", {}).get("n_samples") == 2
    assert size_models.get("lognormal", {}).get("n_samples") == 2
