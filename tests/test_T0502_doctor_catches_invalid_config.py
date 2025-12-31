from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402


def _invalid_doctor_cfg() -> dict[str, Any]:
    return {
        "run_name": "doctor_invalid_param_space",
        "seed": 123,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": "wafer_particles.process.doctor"},
        "wafer_particles": {
            "allow_optional_patterns": False,
            "wafer_radius_mm": 150.0,
            "label_selection": {"mode": "fixed", "labels": ["ring_narrow"]},
            "patterns": {
                "ring_narrow": {
                    "schema_version": "wafer_particles.pattern_config.v1",
                    "name": "wafer_particles.pattern.ring_narrow",
                    "n_particles": 10,
                    "wafer_radius_mm": 150.0,
                    "param_space": {
                        "radius_ratio": {"dist": "uniform", "low": 0.9, "high": 0.1},
                    },
                }
            },
            "size_models": {
                "name": "wafer_particles.size_model.lognormal",
                "mu_log": 0.0,
                "sigma_log": 0.1,
            },
            "io": {"format": "csv"},
        },
    }


def test_doctor_fails_on_invalid_param_space(tmp_path: Path) -> None:
    cfg = _invalid_doctor_cfg()
    with pytest.raises(ValueError, match="doctor validation failed"):
        dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)
