from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402


def _make_cfg(particles_path: str) -> dict[str, Any]:
    return {
        "run_name": "t0403_guard",
        "seed": 0,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": "wafer_particles.process.compare_real"},
        "wafer_particles": {
            "qc": {},
            "compare_real": {
                "real": {
                    "particles_path": particles_path,
                },
                "synthetic": {},
            },
        },
    }


def test_T0403_reject_repo_real_paths(tmp_path: Path) -> None:
    cfg = _make_cfg("real_data.csv")
    with pytest.raises(
        ValueError,
        match="real_data inputs must live outside repository root",
    ):
        dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)
