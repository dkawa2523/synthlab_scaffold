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
from synthlab.framework.registry import get_pattern  # noqa: E402


def _sample_ctx(n_particles: int = 512, wafer_radius_mm: float = 100.0) -> PatternContext:
    return PatternContext(n_particles=n_particles, wafer_radius_mm=wafer_radius_mm)


def _generate(
    pattern_key: str,
    cfg: dict[str, object],
    *,
    seed: int = 123,
    n_particles: int = 512,
) -> list[dict[str, float | str]]:
    rng = random.Random(seed)
    generator = get_pattern(pattern_key)
    return generator.generate(_sample_ctx(n_particles=n_particles), cfg, rng)


def _circular_mean(angles: list[float]) -> float:
    sin_sum = sum(math.sin(angle) for angle in angles)
    cos_sum = sum(math.cos(angle) for angle in angles)
    return math.atan2(sin_sum, cos_sum) % math.tau


def _angular_distance(angle_a: float, angle_b: float) -> float:
    delta = abs(angle_a - angle_b) % math.tau
    if delta > math.pi:
        delta = math.tau - delta
    return delta


def test_edge_sector_custom_angle_bias() -> None:
    center_rad = 2.3
    width_rad = math.radians(30.0)
    cfg = {
        "mode": "custom",
        "angle_center_rad": center_rad,
        "angle_width_rad": width_rad,
        "edge_width_ratio": 0.05,
    }
    particles = _generate("wafer_particles.pattern.edge_sector", cfg, seed=21, n_particles=600)
    thetas = [float(particle["theta_rad"]) for particle in particles]

    mean_angle = _circular_mean(thetas)
    mean_offset = _angular_distance(mean_angle, center_rad)
    assert mean_offset < width_rad * 0.2

    avg_offset = sum(_angular_distance(theta, center_rad) for theta in thetas) / len(thetas)
    assert avg_offset < width_rad * 0.35


def test_composite_ring_hotspot_components() -> None:
    cfg = {
        "components": [
            {
                "pattern": "wafer_particles.pattern.ring_narrow",
                "weight": 0.6,
                "component_label_fine": "ring",
                "cfg": {"radius_ratio": 0.7, "width_ratio": 0.03},
            },
            {
                "pattern": "wafer_particles.pattern.hotspot",
                "weight": 0.4,
                "component_label_fine": "hotspot",
                "cfg": {"mode": "center", "sigma_ratio": 0.04},
            },
        ]
    }
    particles = _generate("wafer_particles.pattern.composite", cfg, seed=5, n_particles=200)

    components = [particle.get("component_label_fine") for particle in particles]
    assert all(component is not None for component in components)
    labels = {str(component) for component in components}
    assert labels == {"ring", "hotspot"}
    assert components.count("ring") > 0
    assert components.count("hotspot") > 0
