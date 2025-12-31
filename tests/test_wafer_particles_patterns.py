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
from synthlab.domains.wafer_particles import polar_to_cartesian_mm  # noqa: E402
from synthlab.domains.wafer_particles.generators.patterns.base import PatternContext  # noqa: E402
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
    "wafer_particles.pattern.pp_inhom_poisson",
    "wafer_particles.pattern.pp_thomas_cluster",
    "wafer_particles.pattern.pp_strauss_repulsive",
]


def _sample_ctx() -> PatternContext:
    return PatternContext(n_particles=64, wafer_radius_mm=100.0)


def _generate(pattern_key: str, cfg: dict[str, object], seed: int = 123) -> list[dict[str, float | str]]:
    rng = random.Random(seed)
    generator = get_pattern(pattern_key)
    return generator.generate(_sample_ctx(), cfg, rng)


def _nearest_neighbor_distances(particles: list[dict[str, float | str]], wafer_radius_mm: float) -> list[float]:
    points = [
        polar_to_cartesian_mm(float(particle["r_norm"]) * wafer_radius_mm, float(particle["theta_rad"]))
        for particle in particles
    ]
    if len(points) < 2:
        return []
    distances: list[float] = []
    for idx, (x_i, y_i) in enumerate(points):
        min_dist = None
        for jdx, (x_j, y_j) in enumerate(points):
            if idx == jdx:
                continue
            dist = math.hypot(x_i - x_j, y_i - y_j)
            if min_dist is None or dist < min_dist:
                min_dist = dist
        if min_dist is not None:
            distances.append(min_dist)
    return distances


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
        (
            "wafer_particles.pattern.pp_inhom_poisson",
            {"mean_particles": 64.0, "radial_power": 1.2, "angular_amplitude": 0.3},
            (1, 512),
        ),
        (
            "wafer_particles.pattern.pp_thomas_cluster",
            {"mean_particles": 64.0, "mean_children": 6.0, "cluster_sigma_ratio": 0.05},
            (1, 512),
        ),
        (
            "wafer_particles.pattern.pp_strauss_repulsive",
            {"n_particles": 64, "min_distance_ratio": 0.02},
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
        r_norm = float(particle["r_norm"])
        theta_rad = float(particle["theta_rad"])
        assert 0.0 <= r_norm <= 1.0 + 1e-6
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
        if key == "wafer_particles.pattern.pp_inhom_poisson":
            cfg = {"mean_particles": 48.0, "radial_power": 1.1, "angular_amplitude": 0.25}
        if key == "wafer_particles.pattern.pp_thomas_cluster":
            cfg = {"mean_particles": 48.0, "mean_children": 6.0, "cluster_sigma_ratio": 0.04}
        if key == "wafer_particles.pattern.pp_strauss_repulsive":
            cfg = {"n_particles": 48, "min_distance_ratio": 0.03}
        out_a = _generate(key, cfg, seed=7)
        out_b = _generate(key, cfg, seed=7)
        assert out_a == out_b


def test_ring_width_changes_distribution() -> None:
    narrow_cfg = {"width_ratio": 0.01}
    wide_cfg = {"width_ratio": 0.2}
    narrow = _generate("wafer_particles.pattern.ring_narrow", narrow_cfg, seed=11)
    wide = _generate("wafer_particles.pattern.ring_narrow", wide_cfg, seed=11)
    narrow_r = [float(particle["r_norm"]) for particle in narrow]
    wide_r = [float(particle["r_norm"]) for particle in wide]
    assert statistics.pstdev(wide_r) > statistics.pstdev(narrow_r) * 5.0


def test_composite_sets_component_label() -> None:
    cfg = {
        "components": [
            {"pattern": "wafer_particles.pattern.ring_narrow", "weight": 0.6, "component_label_fine": "ring"},
            {"pattern": "wafer_particles.pattern.random_uniform", "weight": 0.4, "component_label_fine": "bg"},
        ]
    }
    particles = _generate("wafer_particles.pattern.composite", cfg, seed=5)
    assert all("component_label_fine" in particle for particle in particles)
    assert all("component_id" in particle for particle in particles)
    assert len({particle.get("component_id") for particle in particles}) == 2


def test_composite_transform_radial_scale() -> None:
    cfg = {
        "components": [
            {
                "pattern": "wafer_particles.pattern.ring_narrow",
                "weight": 0.5,
                "component_label_fine": "outer",
                "cfg": {"radius_ratio": 0.7, "width_ratio": 0.02},
            },
            {
                "pattern": "wafer_particles.pattern.ring_narrow",
                "weight": 0.5,
                "component_label_fine": "inner",
                "cfg": {"radius_ratio": 0.7, "width_ratio": 0.02},
                "transform": {"radial_scale": 0.5},
            },
        ]
    }
    particles = _generate("wafer_particles.pattern.composite", cfg, seed=11)
    repeat = _generate("wafer_particles.pattern.composite", cfg, seed=11)
    assert particles == repeat
    outer = [float(particle["r_norm"]) for particle in particles if particle.get("component_label_fine") == "outer"]
    inner = [float(particle["r_norm"]) for particle in particles if particle.get("component_label_fine") == "inner"]
    assert outer and inner
    assert statistics.mean(inner) < statistics.mean(outer) * 0.8


def test_repulsive_enforces_min_distance() -> None:
    cfg = {"n_particles": 40, "min_distance_ratio": 0.06}
    particles = _generate("wafer_particles.pattern.pp_strauss_repulsive", cfg, seed=21)
    distances = _nearest_neighbor_distances(particles, _sample_ctx().wafer_radius_mm)
    assert distances
    min_distance = min(distances)
    expected = _sample_ctx().wafer_radius_mm * cfg["min_distance_ratio"]
    assert min_distance >= expected * 0.95


def test_repulsive_has_larger_nn_than_cluster() -> None:
    cluster_cfg = {"n_parents": 6, "children_per_parent": 8, "cluster_sigma_ratio": 0.02}
    repulsive_cfg = {"n_particles": 48, "min_distance_ratio": 0.05}
    cluster = _generate("wafer_particles.pattern.pp_thomas_cluster", cluster_cfg, seed=11)
    repulsive = _generate("wafer_particles.pattern.pp_strauss_repulsive", repulsive_cfg, seed=11)
    cluster_distances = _nearest_neighbor_distances(cluster, _sample_ctx().wafer_radius_mm)
    repulsive_distances = _nearest_neighbor_distances(repulsive, _sample_ctx().wafer_radius_mm)
    assert cluster_distances
    assert repulsive_distances
    assert statistics.mean(repulsive_distances) > statistics.mean(cluster_distances)
