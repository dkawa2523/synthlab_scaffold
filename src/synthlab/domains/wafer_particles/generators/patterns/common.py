from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, exp, sin, sqrt, tau
from typing import Any, Mapping

from .base import PatternContext

Particle = dict[str, float | str | int]


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
) -> PatternContext:
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

    return PatternContext(n_particles=n_particles, wafer_radius_mm=wafer_radius_mm)


def build_particle(
    r_norm: float,
    theta_rad: float,
    *,
    component_label_fine: str | None = None,
    component_id: int | None = None,
) -> Particle:
    particle: Particle = {"r_norm": _clamp_r_norm(r_norm), "theta_rad": _normalize_theta(theta_rad)}
    if component_label_fine is not None:
        particle["component_label_fine"] = str(component_label_fine)
    if component_id is not None:
        particle["component_id"] = int(component_id)
    return particle


def cartesian_to_polar_norm(x_norm: float, y_norm: float) -> tuple[float, float]:
    r_norm = sqrt(x_norm * x_norm + y_norm * y_norm)
    theta_rad = atan2(y_norm, x_norm)
    return _clamp_r_norm(r_norm), _normalize_theta(theta_rad)


def resolve_radius_norm(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    *,
    default_ratio: float,
) -> float:
    radius_norm = _resolve_norm(cfg, ctx, "radius_norm", "radius_ratio", "radius_mm", default_ratio)
    return _clamp_r_norm(radius_norm)


def resolve_width_norm(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    *,
    default_ratio: float,
) -> float:
    width_norm = _resolve_norm(cfg, ctx, "width_norm", "width_ratio", "width_mm", default_ratio)
    if width_norm <= 0:
        raise ValueError("width must be positive")
    return float(width_norm)


def resolve_length_norm(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    *,
    default_ratio: float,
) -> float:
    length_norm = _resolve_norm(cfg, ctx, "length_norm", "length_ratio", "length_mm", default_ratio)
    if length_norm <= 0:
        raise ValueError("length must be positive")
    return float(length_norm)


def norm_to_mm(r_norm: float, wafer_radius_mm: float) -> float:
    return float(_clamp_r_norm(r_norm) * wafer_radius_mm)


def mm_to_norm(r_mm: float, wafer_radius_mm: float) -> float:
    if wafer_radius_mm <= 0:
        raise ValueError("wafer_radius_mm must be positive")
    return _clamp_r_norm(float(r_mm) / wafer_radius_mm)


def _resolve_norm(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    norm_key: str,
    ratio_key: str,
    mm_key: str,
    default_ratio: float,
) -> float:
    if norm_key in cfg:
        return float(cfg[norm_key])
    if mm_key in cfg:
        return mm_to_norm(float(cfg[mm_key]), ctx.wafer_radius_mm)
    ratio = float(cfg.get(ratio_key, default_ratio))
    return ratio


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


def _clamp_r_norm(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


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


def sample_uniform_disk_xy(rng: Any) -> tuple[float, float]:
    r_norm = sqrt(rng.random())
    theta_rad = rng.random() * tau
    return r_norm * cos(theta_rad), r_norm * sin(theta_rad)
