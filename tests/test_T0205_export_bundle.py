from __future__ import annotations

import hashlib
import sys
import zipfile
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


def _wafer_particles_cfg(taxonomy: dict[str, Any], package_format: str = "none") -> dict[str, Any]:
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
            "split": {
                "mode": "ratio",
                "seed_offset": 0,
                "shuffle": True,
                "ratios": {"train": 0.8, "val": 0.1, "test": 0.1},
            },
            "package": {"format": package_format},
        },
    }


def _make_cfg(
    process_name: str,
    run_name: str,
    seed: int,
    taxonomy: dict[str, Any],
    *,
    package_format: str = "none",
) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": process_name},
        "wafer_particles": _wafer_particles_cfg(taxonomy, package_format=package_format),
    }


def _manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    return read_manifest(manifest_path)


def _read_checksums(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        entries[rel.strip()] = digest
    return entries


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_export_bundle_outputs_and_checksums(tmp_path: Path) -> None:
    taxonomy = _load_taxonomy()
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0205_gen", seed=11, taxonomy=taxonomy)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    export_cfg = _make_cfg("wafer_particles.process.export", "t0205_export", seed=11, taxonomy=taxonomy)
    export_cfg["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run = dispatch_process(cfg=export_cfg, overrides=[], repo_root=tmp_path)

    assert (export_run / "manifest.json").exists()
    assert (export_run / "manifest.yaml").exists()
    assert (export_run / "DATASET_CARD.md").exists()
    assert (export_run / "taxonomy_snapshot.yaml").exists()
    checksums_path = export_run / "checksums.sha256"
    assert checksums_path.exists()

    checksums = _read_checksums(checksums_path)
    expected = {
        "manifest.json",
        "manifest.yaml",
        "DATASET_CARD.md",
        "taxonomy_snapshot.yaml",
        "splits/splits.json",
        "data/particles.csv",
        "data/samples.csv",
        "data/index_samples.csv",
        "data/index_particles.csv",
    }
    assert expected.issubset(checksums.keys())
    for rel, digest in checksums.items():
        file_path = export_run / rel
        assert file_path.exists()
        assert digest == _sha256_file(file_path)


def test_export_dataset_id_stable(tmp_path: Path) -> None:
    taxonomy = _load_taxonomy()
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0205_gen_stable", seed=22, taxonomy=taxonomy)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    export_cfg_a = _make_cfg("wafer_particles.process.export", "t0205_export_a", seed=22, taxonomy=taxonomy)
    export_cfg_a["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run_a = dispatch_process(cfg=export_cfg_a, overrides=[], repo_root=tmp_path)

    export_cfg_b = _make_cfg("wafer_particles.process.export", "t0205_export_b", seed=22, taxonomy=taxonomy)
    export_cfg_b["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run_b = dispatch_process(cfg=export_cfg_b, overrides=[], repo_root=tmp_path)

    dataset_id_a = _manifest(export_run_a).get("dataset_id")
    dataset_id_b = _manifest(export_run_b).get("dataset_id")
    assert dataset_id_a == dataset_id_b


def test_export_package_zip(tmp_path: Path) -> None:
    taxonomy = _load_taxonomy()
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0205_gen_zip", seed=33, taxonomy=taxonomy)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    export_cfg = _make_cfg(
        "wafer_particles.process.export",
        "t0205_export_zip",
        seed=33,
        taxonomy=taxonomy,
        package_format="zip",
    )
    export_cfg["wafer_particles"]["export"]["input"]["run_dir"] = str(gen_run)
    export_run = dispatch_process(cfg=export_cfg, overrides=[], repo_root=tmp_path)

    manifest = _manifest(export_run)
    dataset_id = manifest.get("dataset_id")
    assert dataset_id
    package_path = export_run / "data" / f"dataset_{dataset_id}.zip"
    assert package_path.exists()
    with zipfile.ZipFile(package_path, "r") as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "checksums.sha256" in names
