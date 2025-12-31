from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.domains.wafer_particles.generators.patterns  # noqa: E402,F401
from synthlab.domains.wafer_particles.generators.patterns.base import PatternContext  # noqa: E402
from synthlab.framework.registry import get_pattern, list_patterns  # noqa: E402


PATTERN_CASES = [
    ("wafer_particles.pattern.K01_Donut_Hollow", {"r_inner_ratio": 0.4, "r_outer_ratio": 0.9}),
    (
        "wafer_particles.pattern.K02_SemiRing_Segment",
        {"arc_radius_ratio": 0.7, "width_ratio": 0.1, "span_deg": 160.0, "angle_center_deg": 20.0},
    ),
    (
        "wafer_particles.pattern.K03_Edge_Arc",
        {"arc_radius_ratio": 0.95, "width_ratio": 0.05, "span_deg": 60.0, "angle_center_deg": 45.0},
    ),
    (
        "wafer_particles.pattern.K04_Scratch_Periodic",
        {"angle_deg": 0.0, "length_ratio": 1.0, "width_ratio": 0.01, "spacing_ratio": 0.12, "n_lines": 4},
    ),
    ("wafer_particles.pattern.O01_ReticleRepeat", {"pitch_ratio": 0.2, "tile_ratio": 0.75, "phase_mode": "random"}),
    ("wafer_particles.pattern.O02_Checkerboard", {"pitch_ratio": 0.2, "tile_ratio": 0.9, "phase_mode": "random"}),
]


def _sample_ctx(n_particles: int = 300) -> PatternContext:
    return PatternContext(n_particles=n_particles, wafer_radius_mm=150.0)


@pytest.mark.parametrize("pattern_key,cfg", PATTERN_CASES)
def test_keep_optional_patterns_generate(pattern_key: str, cfg: dict[str, object]) -> None:
    rng = random.Random(123)
    generator = get_pattern(pattern_key)
    particles = generator.generate(_sample_ctx(), cfg, rng)
    assert len(particles) == 300
    for particle in particles:
        r_norm = float(particle["r_norm"])
        theta_rad = float(particle["theta_rad"])
        assert 0.0 <= r_norm <= 1.0 + 1e-6
        assert 0.0 <= theta_rad < math.tau


def test_keep_optional_patterns_registered() -> None:
    keys = set(list_patterns())
    for pattern_key, _cfg in PATTERN_CASES:
        assert pattern_key in keys


def test_optional_patterns_disabled_by_default() -> None:
    cfg_dir = ROOT / "conf" / "wafer_particles" / "patterns"
    for name in ("O01_ReticleRepeat", "O02_Checkerboard"):
        data = yaml.safe_load((cfg_dir / f"{name}.yaml").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise AssertionError(f"{name}.yaml must be a mapping")
        cfg = data.get(name)
        if not isinstance(cfg, dict):
            raise AssertionError(f"{name}.yaml must include top-level {name} mapping")
        assert cfg.get("enabled") is False
