from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.processes  # noqa: E402,F401
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import find_manifest, read_manifest  # noqa: E402

TAXONOMY_PATH = ROOT / "conf" / "wafer_particles" / "labels" / "taxonomy_v1.yaml"


def _load_taxonomy() -> dict[str, Any]:
    data = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("taxonomy_v1.yaml must be a mapping")
    return data


def _write_label_spec(path: Path, *, derived_value: str) -> None:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "name: export_spec",
                "layers:",
                "  family:",
                f"    random_uniform: {derived_value}",
                "similarity_groups:",
                "  - name: group_a",
                "    description: test group",
                "    members: [random_uniform]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _wafer_particles_cfg(taxonomy: dict[str, Any], *, spec_path: Path, apply_labeling: bool) -> dict[str, Any]:
    return {
        "n_samples": 2,
        "n_particles": 6,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": True,
        "source": "synthetic",
        "labels": taxonomy,
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
        "export": {
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "apply_labeling_spec": apply_labeling,
            "labeling_spec_path": str(spec_path),
            "split": {
                "mode": "ratio",
                "seed_offset": 0,
                "shuffle": True,
                "ratios": {"train": 0.8, "val": 0.1, "test": 0.1},
            },
            "package": {"format": "none"},
        },
    }


def _make_cfg(
    process_name: str,
    run_name: str,
    seed: int,
    taxonomy: dict[str, Any],
    *,
    spec_path: Path,
    apply_labeling: bool,
) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": process_name},
        "wafer_particles": _wafer_particles_cfg(taxonomy, spec_path=spec_path, apply_labeling=apply_labeling),
    }


def _manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    return read_manifest(manifest_path)


def test_T0507_export_dataset_id_and_card(tmp_path: Path) -> None:
    taxonomy = _load_taxonomy()
    spec_path = tmp_path / "label_spec.yaml"
    _write_label_spec(spec_path, derived_value="Background")

    gen_cfg = _make_cfg(
        "wafer_particles.process.generate",
        "t0507_gen",
        seed=11,
        taxonomy=taxonomy,
        spec_path=spec_path,
        apply_labeling=False,
    )
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    export_cfg_a = _make_cfg(
        "wafer_particles.process.export",
        "t0507_export_a",
        seed=11,
        taxonomy=taxonomy,
        spec_path=spec_path,
        apply_labeling=True,
    )
    export_cfg_a["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run_a = dispatch_process(cfg=export_cfg_a, overrides=[], repo_root=tmp_path)

    export_cfg_b = _make_cfg(
        "wafer_particles.process.export",
        "t0507_export_b",
        seed=11,
        taxonomy=taxonomy,
        spec_path=spec_path,
        apply_labeling=True,
    )
    export_cfg_b["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run_b = dispatch_process(cfg=export_cfg_b, overrides=[], repo_root=tmp_path)

    dataset_id_a = _manifest(export_run_a).get("dataset_id")
    dataset_id_b = _manifest(export_run_b).get("dataset_id")
    assert dataset_id_a == dataset_id_b

    assert (export_run_a / "DATASET_CARD.md").exists()
    assert (export_run_a / "reports" / "dataset_card.md").exists()

    _write_label_spec(spec_path, derived_value="Changed")
    export_cfg_c = _make_cfg(
        "wafer_particles.process.export",
        "t0507_export_c",
        seed=11,
        taxonomy=taxonomy,
        spec_path=spec_path,
        apply_labeling=True,
    )
    export_cfg_c["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run_c = dispatch_process(cfg=export_cfg_c, overrides=[], repo_root=tmp_path)

    dataset_id_c = _manifest(export_run_c).get("dataset_id")
    assert dataset_id_c != dataset_id_a
