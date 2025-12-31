from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.domains.wafer_particles.labeling import LabelingSpec  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import (  # noqa: E402
    find_manifest,
    paths_from_manifest,
    read_table,
)


def _wafer_particles_cfg() -> dict[str, Any]:
    return {
        "n_samples": 2,
        "n_particles": 8,
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
        "labeling": {"spec_path": None},
        "labeling_apply": {
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.export",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            }
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
            "apply_labeling_spec": False,
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


def test_T0501_labeling_apply(tmp_path: Path) -> None:
    spec_path = tmp_path / "label_spec.yaml"
    spec_path.write_text(
        "\n".join(
            [
                "version: 1",
                "name: test_spec",
                "layers:",
                "  family:",
                "    random_uniform: Background",
                "  location:",
                "    random_uniform: Internal",
                "  geometry:",
                "    random_uniform: Uniform",
                "similarity_groups:",
                "  - name: test_group",
                "    description: test group",
                "    members: [random_uniform]",
                "cause_hypotheses:",
                "  CH_TEST:",
                "    title: test cause",
                "    description: test cause",
                "    confidence: low",
                "    related_labels: [random_uniform]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    gen_cfg = _make_cfg("wafer_particles.process.generate", "label_gen", seed=11)
    gen_run = _run_process(tmp_path, gen_cfg)

    export_cfg = _make_cfg("wafer_particles.process.export", "label_export", seed=11)
    export_cfg["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run = _run_process(tmp_path, export_cfg)

    label_cfg = _make_cfg("wafer_particles.process.labeling_apply", "label_apply", seed=11)
    label_cfg["wafer_particles"]["labeling"]["spec_path"] = str(spec_path)
    label_cfg["wafer_particles"]["labeling_apply"]["input"]["run_dir"] = str(export_run)
    label_run = _run_process(tmp_path, label_cfg)

    particles, samples = _read_tables(label_run)

    for column in ("label_family", "label_location", "label_geometry"):
        assert column in particles[0]
        assert column in samples[0]

    family_values = {row.get("label_family") for row in samples}
    assert "UNKNOWN" in family_values

    hash_path = label_run / "meta" / "labeling_spec_hash.txt"
    assert hash_path.exists()
    assert hash_path.read_text(encoding="utf-8").strip() == LabelingSpec.load(spec_path).hash()

    assert (label_run / "reports" / "labeling_layers_summary.json").exists()
    assert (label_run / "reports" / "similarity_groups_summary.json").exists()
