from __future__ import annotations

import math
import random
import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.domains.wafer_particles.generators.patterns  # noqa: E402,F401
from synthlab.framework.registry import get_pattern, list_patterns  # noqa: E402


PATTERN_KEYS = [
    "wafer_particles.pattern.ring_narrow",
    "wafer_particles.pattern.ring_wide",
    "wafer_particles.pattern.edge_sector",
    "wafer_particles.pattern.scratch",
    "wafer_particles.pattern.radial_lines",
    "wafer_particles.pattern.hotspot",
    "wafer_particles.pattern.random_uniform",
    "wafer_particles.pattern.random_edge_biased",
    "wafer_particles.pattern.inhomogeneous_poisson",
    "wafer_particles.pattern.cluster_parent_child",
    "wafer_particles.pattern.cox_lognormal",
    "wafer_particles.pattern.composite",
]


def _sample_ctx() -> dict[str, float | int]:
    return {"n_particles": 64, "wafer_radius_mm": 100.0}


def _generate(pattern_key: str, cfg: dict[str, object], seed: int = 123) -> list[dict[str, float | str]]:
    rng = random.Random(seed)
    generator = get_pattern(pattern_key)
    return generator(cfg, rng, _sample_ctx())


@pytest.mark.parametrize(
    "pattern_key,cfg,count_range",
    [
        ("wafer_particles.pattern.ring_narrow", {}, (64, 64)),
        ("wafer_particles.pattern.ring_wide", {}, (64, 64)),
        (
            "wafer_particles.pattern.edge_sector",
            {"side": "left", "angle_width_deg": 30.0, "edge_width_ratio": 0.08},
            (64, 64),
        ),
        (
            "wafer_particles.pattern.scratch",
            {"angle_category": "diagonal", "width_ratio": 0.02},
            (64, 64),
        ),
        (
            "wafer_particles.pattern.radial_lines",
            {"n_lines": 5, "angular_jitter_deg": 1.0},
            (64, 64),
        ),
        (
            "wafer_particles.pattern.hotspot",
            {"mode": "edge", "sigma_ratio": 0.04, "center_radius_ratio": 0.9},
            (64, 64),
        ),
        ("wafer_particles.pattern.random_uniform", {}, (64, 64)),
        ("wafer_particles.pattern.random_edge_biased", {"edge_bias": 3.0}, (64, 64)),
        (
            "wafer_particles.pattern.inhomogeneous_poisson",
            {"mean_particles": 64.0, "radial_power": 1.5, "angular_amplitude": 0.4},
            (1, 512),
        ),
        (
            "wafer_particles.pattern.cluster_parent_child",
            {"mean_particles": 64.0, "mean_children": 6.0, "cluster_sigma_ratio": 0.05},
            (1, 512),
        ),
        (
            "wafer_particles.pattern.cox_lognormal",
            {"mean_particles": 64.0, "grid_bins": 6, "field_sigma": 0.8},
            (1, 512),
        ),
        (
            "wafer_particles.pattern.composite",
            {
                "components": [
                    {"pattern": "wafer_particles.pattern.ring_narrow", "weight": 0.7},
                    {"pattern": "wafer_particles.pattern.random_uniform", "weight": 0.3},
                ]
            },
            (64, 64),
        ),
    ],
)
def test_patterns_generate_within_bounds(
    pattern_key: str,
    cfg: dict[str, object],
    count_range: tuple[int, int],
) -> None:
    particles = _generate(pattern_key, cfg)
    ctx = _sample_ctx()
    min_count, max_count = count_range
    assert min_count <= len(particles) <= max_count
    for particle in particles:
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        assert 0.0 <= r_mm <= ctx["wafer_radius_mm"] + 1e-6
        assert 0.0 <= theta_rad < math.tau


def test_pattern_registry_contains_expected_keys() -> None:
    keys = set(list_patterns())
    for key in PATTERN_KEYS:
        assert key in keys


def test_patterns_are_deterministic() -> None:
    for key in PATTERN_KEYS:
        cfg = {}
        if key == "wafer_particles.pattern.edge_sector":
            cfg = {"side": "right", "angle_width_deg": 20.0}
        if key == "wafer_particles.pattern.scratch":
            cfg = {"angle_category": "horizontal"}
        if key == "wafer_particles.pattern.radial_lines":
            cfg = {"n_lines": 4}
        if key == "wafer_particles.pattern.hotspot":
            cfg = {"mode": "center", "sigma_ratio": 0.03}
        if key == "wafer_particles.pattern.random_edge_biased":
            cfg = {"edge_bias": 2.5}
        if key == "wafer_particles.pattern.inhomogeneous_poisson":
            cfg = {"mean_particles": 48.0, "radial_power": 1.0, "angular_amplitude": 0.3}
        if key == "wafer_particles.pattern.cluster_parent_child":
            cfg = {"mean_particles": 48.0, "mean_children": 6.0, "cluster_sigma_ratio": 0.04}
        if key == "wafer_particles.pattern.cox_lognormal":
            cfg = {"mean_particles": 48.0, "grid_bins": 6, "field_sigma": 0.9}
        if key == "wafer_particles.pattern.composite":
            cfg = {
                "components": [
                    {"pattern": "wafer_particles.pattern.ring_narrow", "weight": 0.5},
                    {"pattern": "wafer_particles.pattern.random_uniform", "weight": 0.5},
                ]
            }
        out_a = _generate(key, cfg, seed=7)
        out_b = _generate(key, cfg, seed=7)
        assert out_a == out_b


def test_ring_width_changes_distribution() -> None:
    narrow_cfg = {"width_ratio": 0.01}
    wide_cfg = {"width_ratio": 0.2}
    narrow = _generate("wafer_particles.pattern.ring_narrow", narrow_cfg, seed=11)
    wide = _generate("wafer_particles.pattern.ring_narrow", wide_cfg, seed=11)
    narrow_r = [float(particle["r_mm"]) for particle in narrow]
    wide_r = [float(particle["r_mm"]) for particle in wide]
    assert statistics.pstdev(wide_r) > statistics.pstdev(narrow_r) * 5.0


def test_composite_sets_component_label() -> None:
    cfg = {
        "components": [
            {"pattern": "wafer_particles.pattern.ring_narrow", "weight": 0.6, "label": "ring"},
            {"pattern": "wafer_particles.pattern.random_uniform", "weight": 0.4, "label": "bg"},
        ]
    }
    particles = _generate("wafer_particles.pattern.composite", cfg, seed=5)
    assert all("component" in particle for particle in particles)
