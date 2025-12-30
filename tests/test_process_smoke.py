from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import (  # noqa: E402
    DOMAIN_NAME,
    PARTICLES_SCHEMA,
    SAMPLES_SCHEMA,
    SCHEMA_VERSION,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import (  # noqa: E402
    find_manifest,
    paths_from_manifest,
    read_table,
)


def _wafer_particles_cfg() -> dict[str, Any]:
    return {
        "n_samples": 3,
        "n_particles": 8,
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
        "io": {
            "format": "csv",
        },
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
        "viz": {
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "samples_per_label": 1,
            "max_labels": None,
            "wafer_radius_mm": 10.0,
            "scatter": {"max_points": None, "point_size": 6.0, "alpha": 0.7},
            "hist": {
                "r": {"start": 0.0, "stop": 10.0, "count": 5},
                "theta": {"start": 0.0, "stop": 6.283185307179586, "count": 6},
                "size": {"start": 0.0, "stop": 5.0, "count": 5},
            },
        },
        "export": {
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "split": {
                "mode": "ratio",
                "seed_offset": 0,
                "shuffle": True,
                "ratios": {"train": 0.8, "val": 0.1, "test": 0.1},
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


def _run_process(tmp_path: Path, cfg: dict[str, Any]) -> Path:
    return dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)


def _read_tables(run_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    particles_path, samples_path = paths_from_manifest(
        manifest_path,
        expected_schema_version=SCHEMA_VERSION,
        expected_domain=DOMAIN_NAME,
    )
    particles = read_table(particles_path)
    samples = read_table(samples_path)
    return particles, samples


def test_generate_reproducibility_same_seed(tmp_path: Path) -> None:
    cfg_a = _make_cfg("wafer_particles.process.generate", "run_a", seed=123)
    run_a = _run_process(tmp_path, cfg_a)
    cfg_b = _make_cfg("wafer_particles.process.generate", "run_b", seed=123)
    run_b = _run_process(tmp_path, cfg_b)

    particles_a, samples_a = _read_tables(run_a)
    particles_b, samples_b = _read_tables(run_b)

    assert particles_a == particles_b
    assert samples_a == samples_b


def test_generate_outputs_match_schema(tmp_path: Path) -> None:
    cfg = _make_cfg("wafer_particles.process.generate", "schema_run", seed=7)
    run_dir = _run_process(tmp_path, cfg)
    particles, samples = _read_tables(run_dir)

    validate_particles_table(particles)
    validate_samples_table(samples)

    particle_required = PARTICLES_SCHEMA.required_names()
    sample_required = SAMPLES_SCHEMA.required_names()
    assert all(particle_required.issubset(row.keys()) for row in particles)
    assert all(sample_required.issubset(row.keys()) for row in samples)


def test_smoke_generate_qc_viz(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")

    gen_cfg = _make_cfg("wafer_particles.process.generate", "smoke_generate", seed=99)
    gen_run = _run_process(tmp_path, gen_cfg)

    qc_cfg = _make_cfg("wafer_particles.process.qc", "smoke_qc", seed=99)
    qc_cfg["wafer_particles"]["qc"]["input"]["run_dir"] = str(gen_run)
    qc_run = _run_process(tmp_path, qc_cfg)

    viz_cfg = _make_cfg("wafer_particles.process.viz", "smoke_viz", seed=99)
    viz_cfg["wafer_particles"]["viz"]["input"]["run_dir"] = str(gen_run)
    viz_run = _run_process(tmp_path, viz_cfg)

    assert (qc_run / "metrics" / "qc.json").exists()
    assert (qc_run / "metrics" / "label_summary.csv").exists()
    assert (viz_run / "metrics" / "viz_summary.json").exists()


def test_smoke_export(tmp_path: Path) -> None:
    gen_cfg = _make_cfg("wafer_particles.process.generate", "smoke_export_generate", seed=101)
    gen_run = _run_process(tmp_path, gen_cfg)

    export_cfg = _make_cfg("wafer_particles.process.export", "smoke_export", seed=101)
    export_cfg["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run = _run_process(tmp_path, export_cfg)

    manifest_path = export_run / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("dataset_id")
    assert (export_run / "metrics" / "export_summary.json").exists()
    assert (export_run / "splits" / "splits.json").exists()
    assert (export_run / "data" / "index_samples.csv").exists()
    assert (export_run / "data" / "index_particles.csv").exists()
