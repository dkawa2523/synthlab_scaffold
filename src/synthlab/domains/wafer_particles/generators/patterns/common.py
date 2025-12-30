from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, exp, sin, sqrt, tau
from typing import Any, Mapping

Particle = dict[str, float | str]


@dataclass(frozen=True)
class SampleContext:
    n_particles: int
    wafer_radius_mm: float


def resolve_sample_ctx(
    cfg: Mapping[str, Any],
    sample_ctx: Mapping[str, Any] | SampleContext | None,
    *,
    default_n_particles: int = 100,
    default_wafer_radius_mm: float = 150.0,
) -> SampleContext:
    n_particles = _read_value(sample_ctx, "n_particles", cfg.get("n_particles"))
    if n_particles is None:
        n_particles = default_n_particles
    n_particles = int(n_particles)
    if n_particles <= 0:
        raise ValueError("n_particles must be positive")

    wafer_radius_mm = _read_value(sample_ctx, "wafer_radius_mm", cfg.get("wafer_radius_mm"))
    if wafer_radius_mm is None:
        wafer_radius_mm = default_wafer_radius_mm
    wafer_radius_mm = float(wafer_radius_mm)
    if wafer_radius_mm <= 0:
        raise ValueError("wafer_radius_mm must be positive")

    return SampleContext(n_particles=n_particles, wafer_radius_mm=wafer_radius_mm)


def build_particle(r_mm: float, theta_rad: float, component: str | None = None) -> Particle:
    particle: Particle = {"r_mm": float(r_mm), "theta_rad": _normalize_theta(theta_rad)}
    if component is not None:
        particle["component"] = str(component)
    return particle


def cartesian_to_polar_mm(x_mm: float, y_mm: float) -> tuple[float, float]:
    r_mm = sqrt(x_mm * x_mm + y_mm * y_mm)
    theta_rad = atan2(y_mm, x_mm)
    return r_mm, _normalize_theta(theta_rad)


def resolve_radius_mm(
    cfg: Mapping[str, Any],
    ctx: SampleContext,
    *,
    default_ratio: float,
) -> float:
    radius_mm = cfg.get("radius_mm")
    if radius_mm is None:
        ratio = float(cfg.get("radius_ratio", default_ratio))
        radius_mm = ratio * ctx.wafer_radius_mm
    return _clamp(float(radius_mm), 0.0, ctx.wafer_radius_mm)


def resolve_width_mm(
    cfg: Mapping[str, Any],
    ctx: SampleContext,
    *,
    default_ratio: float,
) -> float:
    width_mm = cfg.get("width_mm")
    if width_mm is None:
        ratio = float(cfg.get("width_ratio", default_ratio))
        width_mm = ratio * ctx.wafer_radius_mm
    width_mm = float(width_mm)
    if width_mm <= 0:
        raise ValueError("width_mm must be positive")
    return width_mm


def _normalize_theta(theta_rad: float) -> float:
    return float(theta_rad) % tau


def _read_value(sample_ctx: Mapping[str, Any] | SampleContext | None, key: str, fallback: Any) -> Any:
    if sample_ctx is None:
        return fallback
    if isinstance(sample_ctx, Mapping):
        if key in sample_ctx:
            return sample_ctx[key]
        return fallback
    value = getattr(sample_ctx, key, None)
    if value is None:
        return fallback
    return value


def _clamp(value: float, min_value: float, max_value: float) -> float:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def sample_poisson(rng: Any, mean: float) -> int:
    if mean <= 0:
        return 0
    if mean > 1000:
        value = rng.gauss(mean, sqrt(mean))
        return max(0, int(round(value)))
    limit = exp(-mean)
    product = 1.0
    count = 0
    while product > limit:
        product *= rng.random()
        count += 1
    return max(0, count - 1)


def sample_uniform_disk_xy(rng: Any, radius_mm: float) -> tuple[float, float]:
    r_mm = radius_mm * sqrt(rng.random())
    theta_rad = rng.random() * tau
    return r_mm * cos(theta_rad), r_mm * sin(theta_rad)
