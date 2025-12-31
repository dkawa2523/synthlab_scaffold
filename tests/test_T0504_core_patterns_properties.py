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
from synthlab.domains.wafer_particles.generators.patterns.base import PatternContext  # noqa: E402
from synthlab.domains.wafer_particles.generators.patterns.geometry import polar_to_cartesian_norm  # noqa: E402
from synthlab.framework.registry import get_pattern, list_patterns  # noqa: E402


PATTERN_KEYS = [
    "wafer_particles.pattern.C01_Uniform",
    "wafer_particles.pattern.C02_EdgeBiased",
    "wafer_particles.pattern.C03_Ring",
    "wafer_particles.pattern.C04_Sector_Edge",
    "wafer_particles.pattern.C05_Sector_Internal",
    "wafer_particles.pattern.C06_RadialLines",
    "wafer_particles.pattern.C07_StraightLine",
    "wafer_particles.pattern.C08_CurvedScratch",
    "wafer_particles.pattern.C09_Spiral",
    "wafer_particles.pattern.C10_Hotspot_Iso",
    "wafer_particles.pattern.C11_Hotspot_Elliptic",
    "wafer_particles.pattern.C12_Crescent_Edge",
    "wafer_particles.pattern.C13_Crescent_Internal",
    "wafer_particles.pattern.C14_EdgeSource_Spray",
    "wafer_particles.pattern.C15_EdgeSource_Bursty",
]


def _sample_ctx(n_particles: int = 400) -> PatternContext:
    return PatternContext(n_particles=n_particles, wafer_radius_mm=100.0)


def _generate(pattern_key: str, cfg: dict[str, object], seed: int = 123, n_particles: int = 400) -> list[dict[str, float | str]]:
    rng = random.Random(seed)
    generator = get_pattern(pattern_key)
    return generator.generate(_sample_ctx(n_particles), cfg, rng)


def _angular_distance(a: float, b: float) -> float:
    diff = (a - b + math.pi) % (2.0 * math.pi) - math.pi
    return abs(diff)


def _covariance(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    cov_xx = statistics.mean((x - mean_x) ** 2 for x in xs)
    cov_yy = statistics.mean((y - mean_y) ** 2 for y in ys)
    cov_xy = statistics.mean((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return cov_xx, cov_yy, cov_xy


@pytest.mark.parametrize(
    "pattern_key,cfg",
    [
        ("wafer_particles.pattern.C01_Uniform", {}),
        ("wafer_particles.pattern.C02_EdgeBiased", {"edge_bias": 2.2}),
        ("wafer_particles.pattern.C03_Ring", {"radius_ratio": 0.7, "width_ratio": 0.08}),
        (
            "wafer_particles.pattern.C04_Sector_Edge",
            {
                "angle_center_deg": 30.0,
                "angle_width_deg": 50.0,
                "edge_width_ratio": 0.2,
                "theta_vonmises_kappa": 4.0,
                "radial_beta_alpha": 2.0,
                "radial_beta_beta": 1.2,
            },
        ),
        (
            "wafer_particles.pattern.C05_Sector_Internal",
            {
                "angle_center_deg": 120.0,
                "angle_width_deg": 60.0,
                "r_inner_ratio": 0.15,
                "r_outer_ratio": 0.75,
                "edge_margin_norm": 0.05,
            },
        ),
        (
            "wafer_particles.pattern.C06_RadialLines",
            {"n_lines": 5, "angular_jitter_deg": 2.0, "r_min_ratio": 0.1, "r_max_ratio": 0.9},
        ),
        (
            "wafer_particles.pattern.C07_StraightLine",
            {"angle_deg": 10.0, "segment_half_length_ratio": 0.5, "width_ratio": 0.03},
        ),
        (
            "wafer_particles.pattern.C08_CurvedScratch",
            {"arc_radius_ratio": 0.75, "span_deg": 80.0, "width_ratio": 0.03},
        ),
        (
            "wafer_particles.pattern.C09_Spiral",
            {"theta_max": math.tau, "start_r_ratio": 0.1, "end_r_ratio": 0.9, "width_ratio": 0.02},
        ),
        ("wafer_particles.pattern.C10_Hotspot_Iso", {"mode": "center", "sigma_ratio": 0.05}),
        (
            "wafer_particles.pattern.C11_Hotspot_Elliptic",
            {"mode": "center", "sigma_x_ratio": 0.08, "sigma_y_ratio": 0.02, "rotation_deg": 30.0},
        ),
        (
            "wafer_particles.pattern.C12_Crescent_Edge",
            {"outer_radius_norm": 1.0, "inner_radius_ratio": 0.75, "offset_ratio": 0.3},
        ),
        (
            "wafer_particles.pattern.C13_Crescent_Internal",
            {"outer_radius_ratio": 0.7, "inner_radius_ratio": 0.55, "offset_ratio": 0.25},
        ),
        (
            "wafer_particles.pattern.C14_EdgeSource_Spray",
            {"angle_center_deg": 0.0, "angle_width_deg": 15.0, "radial_scale_norm": 0.05},
        ),
        (
            "wafer_particles.pattern.C15_EdgeSource_Bursty",
            {
                "angle_center_deg": 0.0,
                "angle_width_deg": 12.0,
                "radial_scale_norm": 0.06,
                "bursts": 3,
                "burst_angle_jitter_deg": 12.0,
            },
        ),
    ],
)
def test_core_patterns_within_bounds(pattern_key: str, cfg: dict[str, object]) -> None:
    particles = _generate(pattern_key, cfg)
    for particle in particles:
        r_norm = float(particle["r_norm"])
        theta_rad = float(particle["theta_rad"])
        assert 0.0 <= r_norm <= 1.0 + 1e-6
        assert 0.0 <= theta_rad < math.tau


def test_core_pattern_registry_contains_keys() -> None:
    keys = set(list_patterns())
    for key in PATTERN_KEYS:
        assert key in keys


def test_c01_uniform_radial_mean() -> None:
    particles = _generate("wafer_particles.pattern.C01_Uniform", {}, n_particles=800)
    r_vals = [float(p["r_norm"]) for p in particles]
    mean_r = statistics.mean(r_vals)
    assert 0.6 < mean_r < 0.72


def test_c02_edge_biased_is_outer() -> None:
    particles = _generate("wafer_particles.pattern.C02_EdgeBiased", {"edge_bias": 2.5}, n_particles=800)
    r_vals = [float(p["r_norm"]) for p in particles]
    assert statistics.mean(r_vals) > 0.75


def test_c03_ring_radial_std_is_small() -> None:
    particles = _generate(
        "wafer_particles.pattern.C03_Ring",
        {"radius_ratio": 0.7, "width_ratio": 0.04},
        n_particles=600,
    )
    r_vals = [float(p["r_norm"]) for p in particles]
    assert statistics.pstdev(r_vals) < 0.05


def test_c04_sector_edge_is_constrained() -> None:
    cfg = {
        "angle_center_deg": 45.0,
        "angle_width_deg": 40.0,
        "edge_width_ratio": 0.2,
        "theta_vonmises_kappa": 4.0,
        "radial_beta_alpha": 2.0,
        "radial_beta_beta": 1.2,
    }
    particles = _generate("wafer_particles.pattern.C04_Sector_Edge", cfg, n_particles=500)
    r_vals = [float(p["r_norm"]) for p in particles]
    assert statistics.mean(r_vals) > 0.82
    center_rad = math.radians(cfg["angle_center_deg"])
    half_width = math.radians(cfg["angle_width_deg"]) * 0.5
    for particle in particles:
        theta = float(particle["theta_rad"])
        assert _angular_distance(theta, center_rad) <= half_width + 1e-6


def test_c05_sector_internal_stays_inside() -> None:
    cfg = {
        "angle_center_deg": 90.0,
        "angle_width_deg": 60.0,
        "r_inner_ratio": 0.2,
        "r_outer_ratio": 0.7,
        "edge_margin_norm": 0.05,
    }
    particles = _generate("wafer_particles.pattern.C05_Sector_Internal", cfg, n_particles=500)
    r_vals = [float(p["r_norm"]) for p in particles]
    assert max(r_vals) <= cfg["r_outer_ratio"] + 1e-6
    assert statistics.mean(r_vals) < 0.75


def test_c06_radial_lines_angles_cluster() -> None:
    cfg = {
        "n_lines": 4,
        "angular_jitter_deg": 1.0,
        "r_min_ratio": 0.2,
        "r_max_ratio": 0.9,
        "sigma_perp_ratio": 0.005,
    }
    particles = _generate("wafer_particles.pattern.C06_RadialLines", cfg, n_particles=600)
    angles = [0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0]
    distances = []
    r_vals = []
    for particle in particles:
        theta = float(particle["theta_rad"])
        distances.append(min(_angular_distance(theta, ref) for ref in angles))
        r_vals.append(float(particle["r_norm"]))
    assert statistics.mean(distances) < 0.25
    assert min(r_vals) >= cfg["r_min_ratio"] - 1e-6
    assert max(r_vals) <= cfg["r_max_ratio"] + 1e-6


def test_c07_straight_line_is_line_like() -> None:
    cfg = {
        "angle_deg": 0.0,
        "segment_half_length_ratio": 0.6,
        "width_ratio": 0.01,
        "offset_ratio": 0.0,
    }
    particles = _generate("wafer_particles.pattern.C07_StraightLine", cfg, n_particles=500)
    xs: list[float] = []
    ys: list[float] = []
    for particle in particles:
        x_norm, y_norm = polar_to_cartesian_norm(float(particle["r_norm"]), float(particle["theta_rad"]))
        xs.append(x_norm)
        ys.append(y_norm)
    assert statistics.pstdev(xs) > statistics.pstdev(ys) * 5.0
    assert statistics.mean(abs(y) for y in ys) < 0.03


def test_c08_curved_scratch_band() -> None:
    cfg = {"arc_radius_ratio": 0.75, "span_deg": 90.0, "width_ratio": 0.02}
    particles = _generate("wafer_particles.pattern.C08_CurvedScratch", cfg, n_particles=500)
    r_vals = [float(p["r_norm"]) for p in particles]
    r_min = cfg["arc_radius_ratio"] - cfg["width_ratio"] * 0.5
    r_max = cfg["arc_radius_ratio"] + cfg["width_ratio"] * 0.5
    assert min(r_vals) >= r_min - 1e-6
    assert max(r_vals) <= r_max + 1e-6


def test_c09_spiral_has_positive_correlation() -> None:
    cfg = {"theta_max": math.tau, "start_r_ratio": 0.1, "end_r_ratio": 0.9, "width_ratio": 0.01}
    particles = _generate("wafer_particles.pattern.C09_Spiral", cfg, n_particles=600)
    thetas = [float(p["theta_rad"]) for p in particles]
    r_vals = [float(p["r_norm"]) for p in particles]
    mean_theta = statistics.mean(thetas)
    mean_r = statistics.mean(r_vals)
    cov = statistics.mean((t - mean_theta) * (r - mean_r) for t, r in zip(thetas, r_vals))
    std_theta = statistics.pstdev(thetas)
    std_r = statistics.pstdev(r_vals)
    corr = cov / (std_theta * std_r)
    assert corr > 0.4


def test_c10_hotspot_iso_isotropic() -> None:
    particles = _generate("wafer_particles.pattern.C10_Hotspot_Iso", {"mode": "center", "sigma_ratio": 0.05})
    xs: list[float] = []
    ys: list[float] = []
    for particle in particles:
        x_norm, y_norm = polar_to_cartesian_norm(float(particle["r_norm"]), float(particle["theta_rad"]))
        xs.append(x_norm)
        ys.append(y_norm)
    std_x = statistics.pstdev(xs)
    std_y = statistics.pstdev(ys)
    ratio = std_x / std_y
    assert 0.8 <= ratio <= 1.2


def test_c11_hotspot_elliptic_anisotropy() -> None:
    cfg = {"mode": "center", "sigma_x_ratio": 0.08, "sigma_y_ratio": 0.02, "rotation_deg": 30.0}
    particles = _generate("wafer_particles.pattern.C11_Hotspot_Elliptic", cfg, n_particles=700)
    xs: list[float] = []
    ys: list[float] = []
    for particle in particles:
        x_norm, y_norm = polar_to_cartesian_norm(float(particle["r_norm"]), float(particle["theta_rad"]))
        xs.append(x_norm)
        ys.append(y_norm)
    cov_xx, cov_yy, cov_xy = _covariance(xs, ys)
    trace = cov_xx + cov_yy
    det = cov_xx * cov_yy - cov_xy * cov_xy
    sqrt_term = math.sqrt(max(0.0, trace * trace / 4.0 - det))
    eig_max = trace / 2.0 + sqrt_term
    eig_min = trace / 2.0 - sqrt_term
    assert eig_min > 0
    assert eig_max / eig_min > 2.0
    assert abs(cov_xy) > 0.0005


def test_c12_crescent_edge_touches_edge() -> None:
    cfg = {"outer_radius_norm": 1.0, "inner_radius_ratio": 0.75, "offset_ratio": 0.3}
    particles = _generate("wafer_particles.pattern.C12_Crescent_Edge", cfg, n_particles=500)
    r_vals = [float(p["r_norm"]) for p in particles]
    assert max(r_vals) > 0.97
    assert statistics.mean(r_vals) > 0.7


def test_c13_crescent_internal_stays_inside() -> None:
    cfg = {"outer_radius_ratio": 0.7, "inner_radius_ratio": 0.55, "offset_ratio": 0.25}
    particles = _generate("wafer_particles.pattern.C13_Crescent_Internal", cfg, n_particles=500)
    r_vals = [float(p["r_norm"]) for p in particles]
    assert max(r_vals) <= cfg["outer_radius_ratio"] + 1e-6


def test_c14_edge_source_spray_is_edge() -> None:
    cfg = {"angle_center_deg": 0.0, "angle_width_deg": 12.0, "radial_scale_norm": 0.05}
    particles = _generate("wafer_particles.pattern.C14_EdgeSource_Spray", cfg, n_particles=600)
    r_vals = [float(p["r_norm"]) for p in particles]
    assert statistics.mean(r_vals) > 0.9


def test_c15_edge_source_bursty_has_multiple_peaks() -> None:
    cfg = {
        "angle_center_deg": 0.0,
        "angle_width_deg": 12.0,
        "radial_scale_norm": 0.06,
        "bursts": 3,
        "burst_angle_jitter_deg": 12.0,
    }
    particles = _generate("wafer_particles.pattern.C15_EdgeSource_Bursty", cfg, n_particles=800)
    r_vals = [float(p["r_norm"]) for p in particles]
    assert statistics.mean(r_vals) > 0.9
    angles = [float(p["theta_rad"]) for p in particles]
    bins = [0 for _ in range(12)]
    for theta in angles:
        idx = int(theta / math.tau * len(bins)) % len(bins)
        bins[idx] += 1
    mean_count = statistics.mean(bins)
    std_count = statistics.pstdev(bins)
    peaks = [count for count in bins if count > mean_count + 1.5 * std_count]
    assert len(peaks) >= 2
