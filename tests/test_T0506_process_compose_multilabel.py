from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.domains.wafer_particles.labeling import normalize_label_list  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import (  # noqa: E402
    find_manifest,
    paths_from_manifest,
    read_table,
)


def _wafer_particles_cfg() -> dict[str, Any]:
    return {
        "n_samples": 4,
        "n_particles": 6,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
        "source": "synthetic",
        "label_selection": {
            "mode": "fixed",
            "labels": ["random_uniform", "ring_narrow"],
            "shuffle": False,
        },
        "patterns": {
            "random_uniform": {"name": "wafer_particles.pattern.random_uniform"},
            "ring_narrow": {"name": "wafer_particles.pattern.ring_narrow"},
        },
        "size_models": {
            "name": "wafer_particles.size_model.lognormal",
            "mu_log": 0.0,
            "sigma_log": 0.1,
        },
        "io": {"format": "csv"},
        "compose": {
            "input_run_dir": None,
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "n_samples_out": 2,
            "n_components": {"value": 2},
            "component_sampling": {"allow_duplicates": False, "weights": None},
            "particle_budget": {"mode": "all"},
            "sample_id_prefix": "compose",
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


def test_T0506_process_compose_multilabel(tmp_path: Path) -> None:
    gen_cfg = _make_cfg("wafer_particles.process.generate", "compose_input", seed=21)
    gen_run = _run_process(tmp_path, gen_cfg)

    compose_cfg = _make_cfg("wafer_particles.process.compose", "compose_out", seed=21)
    compose_cfg["wafer_particles"]["compose"]["input"]["run_dir"] = str(gen_run)
    compose_run = _run_process(tmp_path, compose_cfg)

    particles, samples = _read_tables(compose_run)

    assert "component_id" in particles[0]
    assert "component_label_fine" in particles[0]
    assert "labels_fine" in samples[0]

    expected_labels = {"random_uniform", "ring_narrow"}
    for sample in samples:
        labels = set(normalize_label_list(sample.get("labels_fine")))
        assert labels == expected_labels
        assert sample.get("label_fine_primary") in expected_labels
        assert sample.get("label") == sample.get("label_fine_primary")
        sample_id = sample["sample_id"]
        component_labels = {
            row.get("component_label_fine")
            for row in particles
            if row.get("sample_id") == sample_id
        }
        assert component_labels == expected_labels
        assert sample["n_particles"] == sum(
            1 for row in particles if row.get("sample_id") == sample_id
        )

    compose_cfg_b = _make_cfg("wafer_particles.process.compose", "compose_out_b", seed=21)
    compose_cfg_b["wafer_particles"]["compose"]["input"]["run_dir"] = str(gen_run)
    compose_run_b = _run_process(tmp_path, compose_cfg_b)

    particles_b, samples_b = _read_tables(compose_run_b)
    assert particles == particles_b
    assert samples == samples_b
