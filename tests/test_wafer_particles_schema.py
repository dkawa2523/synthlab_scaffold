from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.domains.wafer_particles import (  # noqa: E402
    SCHEMA_VERSION,
    SchemaValidationError,
    build_manifest,
    polar_to_cartesian_mm,
    validate_manifest,
    validate_particles_table,
    validate_samples_table,
)


def _sample_tables() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    samples = [
        {
            "sample_id": "s1",
            "label": "ring",
            "n_particles": 2,
            "pattern_params": '{"pattern":"ring"}',
            "seed_offset": 0,
        },
        {
            "sample_id": "s2",
            "label": "dot",
            "n_particles": 1,
            "pattern_params": '{"pattern":"dot"}',
            "seed_offset": 1,
        },
    ]

    particle_defs = [
        ("s1", 0, 0.4, 1.0, 0.0, 1.5, "ring"),
        ("s1", 1, 0.45, 1.0, math.pi / 2.0, 1.4, "ring"),
        ("s2", 0, 0.8, 2.0, math.pi, 2.1, "dot"),
    ]
    particles: list[dict[str, object]] = []
    for sample_id, particle_id, r_norm, r_mm, theta_rad, size_um, label in particle_defs:
        x_mm, y_mm = polar_to_cartesian_mm(float(r_mm), float(theta_rad))
        particles.append(
            {
                "sample_id": sample_id,
                "particle_id": particle_id,
                "r_norm": r_norm,
                "r_mm": r_mm,
                "theta_rad": theta_rad,
                "size_um": size_um,
                "label_fine": label,
                "label": label,
                "x_mm": x_mm,
                "y_mm": y_mm,
            }
        )
    return samples, particles


def test_schema_validation_round_trip() -> None:
    samples, particles = _sample_tables()
    validate_samples_table(samples)
    validate_particles_table(particles)
    manifest = build_manifest(
        particles_path="data/particles.parquet",
        samples_path="data/samples.parquet",
        particles_rows=len(particles),
        samples_rows=len(samples),
        label_distribution={"ring": 2, "dot": 1},
    )
    assert manifest["schema_version"] == SCHEMA_VERSION
    validate_manifest(manifest)


def test_particles_schema_requires_columns() -> None:
    _, particles = _sample_tables()
    bad_row = dict(particles[0])
    bad_row.pop("label_fine")
    with pytest.raises(SchemaValidationError):
        validate_particles_table([bad_row])
