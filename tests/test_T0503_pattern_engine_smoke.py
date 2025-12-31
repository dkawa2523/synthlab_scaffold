from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.domains.wafer_particles.generators.patterns  # noqa: E402,F401
from synthlab.domains.wafer_particles.generators.patterns.base import PatternContext  # noqa: E402
from synthlab.domains.wafer_particles.generators.patterns.catalog import load_pattern_catalog  # noqa: E402
from synthlab.domains.wafer_particles.schema import validate_particles_table  # noqa: E402
from synthlab.framework.registry import get_pattern  # noqa: E402


def test_pattern_catalog_smoke() -> None:
    wp_cfg = {
        "patterns": {
            "ring_narrow": {
                "name": "wafer_particles.pattern.ring_narrow",
                "enabled": True,
                "radius_ratio": 0.7,
                "width_ratio": 0.02,
            },
            "edge_sector_right": {
                "name": "wafer_particles.pattern.edge_sector",
                "enabled": True,
                "side": "right",
                "angle_width_deg": 30.0,
                "edge_width_ratio": 0.08,
            },
            "disabled_pattern": {
                "name": "wafer_particles.pattern.random_uniform",
                "enabled": False,
            },
        }
    }
    catalog = load_pattern_catalog(wp_cfg)
    enabled = catalog.enabled_entries()
    assert "ring_narrow" in enabled
    assert "edge_sector_right" in enabled
    assert "disabled_pattern" not in enabled

    ctx = PatternContext(n_particles=32, wafer_radius_mm=100.0)
    rng = random.Random(42)
    for label, entry in enabled.items():
        pattern = get_pattern(entry.pattern_id)
        particles = pattern.generate(ctx, entry.cfg, rng)
        assert len(particles) == ctx.n_particles
        rows = []
        for idx, particle in enumerate(particles):
            r_norm = float(particle["r_norm"])
            theta_rad = float(particle["theta_rad"])
            assert 0.0 <= r_norm <= 1.0 + 1e-6
            assert 0.0 <= theta_rad < math.tau
            rows.append(
                {
                    "sample_id": "sample_000000",
                    "particle_id": idx,
                    "r_norm": r_norm,
                    "r_mm": r_norm * ctx.wafer_radius_mm,
                    "theta_rad": theta_rad,
                    "size_um": 1.0,
                    "label_fine": label,
                    "label": label,
                }
            )
        validate_particles_table(rows)
