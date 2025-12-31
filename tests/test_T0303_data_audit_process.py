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
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION, build_manifest  # noqa: E402
from synthlab.framework.artifacts import ArtifactWriter  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _make_bad_artifact(tmp_path: Path) -> Path:
    cfg = {
        "run_name": "t0303_input",
        "seed": 123,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": "wafer_particles.process.generate"},
    }
    writer = ArtifactWriter(repo_root=tmp_path, cfg=cfg, overrides=[])
    writer.prepare()

    run_dir = writer.run_dir
    particles_rows = [
        {
            "sample_id": "s1",
            "particle_id": 1,
            "r_norm": 0.1,
            "r_mm": 10.0,
            "theta_rad": 1.0,
            "size_um": 5.0,
            "label_fine": "ring_narrow",
            "label": "ring_narrow",
        },
        {
            "sample_id": "s1",
            "particle_id": 1,
            "r_norm": 0.1,
            "r_mm": 10.0,
            "theta_rad": 1.0,
            "size_um": 5.0,
            "label_fine": "ring_narrow",
            "label": "ring_narrow",
        },
        {
            "sample_id": "s1",
            "particle_id": 1,
            "r_norm": 0.12,
            "r_mm": 12.0,
            "theta_rad": 1.1,
            "size_um": 6.0,
            "label_fine": "ring_narrow",
            "label": "ring_narrow",
        },
        {
            "sample_id": "s2",
            "particle_id": 2,
            "r_norm": 0.0,
            "r_mm": -1.0,
            "theta_rad": 0.5,
            "size_um": 4.0,
            "label_fine": "ring_narrow",
            "label": "ring_narrow",
        },
        {
            "sample_id": "s3",
            "particle_id": 3,
            "r_norm": 1.0,
            "r_mm": 160.0,
            "theta_rad": 7.0,
            "size_um": 0.0,
            "label_fine": "",
            "label": "",
        },
    ]
    samples_rows = [
        {
            "sample_id": "s1",
            "label": "ring_narrow",
            "n_particles": 3,
            "pattern_params": "{}",
            "seed_offset": 0,
        },
        {
            "sample_id": "s2",
            "label": "ring_narrow",
            "n_particles": 1,
            "pattern_params": "{}",
            "seed_offset": 1,
        },
        {
            "sample_id": "s3",
            "label": "ring_narrow",
            "n_particles": 1,
            "pattern_params": "{}",
            "seed_offset": 2,
        },
    ]
    particles_path = run_dir / "data" / "particles.csv"
    samples_path = run_dir / "data" / "samples.csv"
    _write_csv(
        particles_path,
        ["sample_id", "particle_id", "r_norm", "r_mm", "theta_rad", "size_um", "label_fine", "label"],
        particles_rows,
    )
    _write_csv(
        samples_path,
        ["sample_id", "label", "n_particles", "pattern_params", "seed_offset"],
        samples_rows,
    )

    manifest = build_manifest(
        particles_path="data/particles.csv",
        samples_path="data/samples.csv",
        particles_rows=len(particles_rows),
        samples_rows=len(samples_rows),
        schema_version=SCHEMA_VERSION,
        domain=DOMAIN_NAME,
    )
    writer.write_json("manifest.json", manifest)
    writer.write_json(
        "splits/splits.json",
        {
            "sample_ids": {
                "train": ["s1", "s2"],
                "val": ["s1"],
                "test": ["s3"],
            }
        },
    )
    writer.finalize()
    return run_dir


def _audit_cfg(run_name: str, input_run_dir: Path) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": 321,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": "wafer_particles.process.audit"},
        "wafer_particles": {
            "audit": {
                "input": {
                    "run_name": None,
                    "process_name": "wafer_particles.process.generate",
                    "run_dir": str(input_run_dir),
                    "manifest_path": None,
                    "particles_path": None,
                    "samples_path": None,
                }
            }
        },
    }


def test_T0303_audit_detects_bad_rows(tmp_path: Path) -> None:
    input_run = _make_bad_artifact(tmp_path)
    cfg = _audit_cfg("t0303_audit", input_run)
    audit_run = dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)

    payload = json.loads((audit_run / "metrics" / "audit.json").read_text(encoding="utf-8"))
    assert payload["summary"]["audit_failed"] is True

    checks = {check["name"]: check for check in payload["checks"]}
    expected_errors = {
        "particles.missing_values",
        "particles.range.r_mm",
        "particles.range.theta_rad",
        "particles.range.size_um",
        "particles.duplicates.sample_particle",
        "particles.duplicates.rows",
        "splits.sample_id_overlap",
    }
    for name in expected_errors:
        assert name in checks
        assert checks[name]["severity"] == "error"
