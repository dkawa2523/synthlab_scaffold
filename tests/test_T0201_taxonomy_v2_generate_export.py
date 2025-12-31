from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import find_manifest, paths_from_manifest, read_table  # noqa: E402

TAXONOMY_PATH = ROOT / "conf" / "wafer_particles" / "labels" / "taxonomy_v2.yaml"


def _load_taxonomy() -> dict[str, Any]:
    data = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("taxonomy_v2.yaml must be a mapping")
    return data


def _label_meta_map(taxonomy: dict[str, Any]) -> dict[str, dict[str, str | None]]:
    entries = taxonomy.get("labels")
    if not isinstance(entries, list):
        return {}
    mapping: dict[str, dict[str, str | None]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        coarse = entry.get("coarse") or entry.get("category")
        family = entry.get("family")
        mapping[str(name)] = {
            "coarse": str(coarse) if coarse is not None else None,
            "family": str(family) if family is not None else None,
        }
        variants = entry.get("variants") or []
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            variant_name = variant.get("name")
            if not variant_name:
                continue
            variant_coarse = variant.get("coarse") or variant.get("category") or coarse
            variant_family = variant.get("family") or family
            mapping[str(variant_name)] = {
                "coarse": str(variant_coarse) if variant_coarse is not None else None,
                "family": str(variant_family) if variant_family is not None else None,
            }
    return mapping


def _wafer_particles_cfg(taxonomy: dict[str, Any]) -> dict[str, Any]:
    return {
        "n_samples": 3,
        "n_particles": 12,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": False,
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
        "io": {"format": "csv"},
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


def _make_cfg(process_name: str, run_name: str, seed: int, taxonomy: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": process_name},
        "wafer_particles": _wafer_particles_cfg(taxonomy),
    }


def _read_samples(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    _particles_path, samples_path = paths_from_manifest(
        manifest_path,
        expected_schema_version=SCHEMA_VERSION,
        expected_domain=DOMAIN_NAME,
    )
    return read_table(samples_path)


def test_taxonomy_v2_generate_export_label_coarse(tmp_path: Path) -> None:
    taxonomy = _load_taxonomy()
    label_meta = _label_meta_map(taxonomy)

    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0201_gen", seed=1, taxonomy=taxonomy)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    samples = _read_samples(gen_run)
    assert samples
    for row in samples:
        label = str(row.get("label"))
        expected = label_meta.get(label)
        assert expected is not None
        assert row.get("label_coarse") == expected.get("coarse")
        if expected.get("family") is not None:
            assert row.get("label_family") == expected.get("family")

    export_cfg = _make_cfg("wafer_particles.process.export", "t0201_export", seed=1, taxonomy=taxonomy)
    export_cfg["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run = dispatch_process(cfg=export_cfg, overrides=[], repo_root=tmp_path)

    export_samples = _read_samples(export_run)
    assert export_samples
    for row in export_samples:
        label = str(row.get("label"))
        expected = label_meta.get(label)
        assert expected is not None
        assert row.get("label_coarse") == expected.get("coarse")
        if expected.get("family") is not None:
            assert row.get("label_family") == expected.get("family")
