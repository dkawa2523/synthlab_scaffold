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


BASE_KEYS = {"min_um", "max_um", "per_sample"}
MODEL_KEYS = {
    "gaussian": {"mean_um", "std_um"},
    "lognormal": {"mu_log", "sigma_log"},
    "weibull": {"k", "lambda_um"},
    "pareto": {"alpha", "xm_um"},
}


def _wafer_particles_cfg() -> dict[str, Any]:
    return {
        "n_samples": 5,
        "n_particles": 4,
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
                "shuffle": False,
                "ratios": {
                    "gaussian": 1.0,
                    "lognormal": 1.0,
                    "weibull": 1.0,
                    "pareto": 1.0,
                    "mixture": 1.0,
                },
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
                "weibull": {
                    "type": "weibull",
                    "k": 1.6,
                    "lambda_um": 0.4,
                },
                "pareto": {
                    "type": "pareto",
                    "alpha": 2.5,
                    "xm_um": 0.1,
                },
                "mixture": {
                    "type": "mixture",
                    "components": [
                        {
                            "name": "base",
                            "weight": 0.7,
                            "model": {
                                "type": "gaussian",
                                "mean_um": 0.2,
                                "std_um": 0.05,
                            },
                        },
                        {
                            "name": "tail",
                            "weight": 0.3,
                            "model": {
                                "type": "lognormal",
                                "mu_log": -0.5,
                                "sigma_log": 0.4,
                            },
                        },
                    ],
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


def _assert_keys(payload: dict[str, Any], keys: set[str]) -> None:
    for key in keys:
        assert key in payload


def test_T0704_size_params_json_keys(tmp_path: Path) -> None:
    cfg = _make_cfg("t0704_size_params_json", seed=21)
    run_dir = dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)

    samples = _read_samples(run_dir)
    assert samples
    for row in samples:
        assert "size_model" in row
        assert "size_params_json" in row
        params = json.loads(row["size_params_json"])
        assert isinstance(params, dict)
        _assert_keys(params, BASE_KEYS)
        assert isinstance(params["per_sample"], bool)

        model = row["size_model"]
        if model in MODEL_KEYS:
            _assert_keys(params, MODEL_KEYS[model])
        elif model == "mixture":
            components = params.get("components")
            assert isinstance(components, list)
            assert components
            for component in components:
                assert isinstance(component, dict)
                _assert_keys(component, {"name", "weight", "model_type", "params"})
                model_type = component.get("model_type")
                assert model_type in MODEL_KEYS
                nested = component.get("params")
                assert isinstance(nested, dict)
                _assert_keys(nested, BASE_KEYS)
                _assert_keys(nested, MODEL_KEYS[model_type])
        else:
            raise AssertionError(f"unexpected size_model: {model}")
