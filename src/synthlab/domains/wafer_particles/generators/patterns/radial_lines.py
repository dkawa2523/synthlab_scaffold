from __future__ import annotations

from math import radians, tau
from typing import Any, Iterable, Mapping

from synthlab.framework.registry import register_pattern

from .common import build_particle, resolve_sample_ctx


@register_pattern("wafer_particles.pattern.radial_lines")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    angles_rad = _resolve_angles_rad(cfg)
    angular_jitter_rad = _resolve_jitter_rad(cfg)
    r_min, r_max = _resolve_radius_range(cfg, ctx.wafer_radius_mm)

    particles: list[dict[str, float | str]] = []
    for _ in range(ctx.n_particles):
        angle = angles_rad[int(rng.random() * len(angles_rad))]
        theta_rad = angle + (rng.random() - 0.5) * 2.0 * angular_jitter_rad
        r_mm = rng.uniform(r_min, r_max)
        particles.append(build_particle(r_mm, theta_rad))
    return particles


def _resolve_angles_rad(cfg: Mapping[str, Any]) -> list[float]:
    if "angles_rad" in cfg:
        return [float(value) for value in _ensure_iterable(cfg["angles_rad"])]
    if "angles_deg" in cfg:
        return [radians(float(value)) for value in _ensure_iterable(cfg["angles_deg"])]
    n_lines = int(cfg.get("n_lines", 6))
    if n_lines <= 0:
        raise ValueError("n_lines must be positive")
    offset = float(cfg.get("angle_offset_rad", 0.0))
    return [offset + tau * idx / n_lines for idx in range(n_lines)]


def _resolve_jitter_rad(cfg: Mapping[str, Any]) -> float:
    if "angular_jitter_rad" in cfg:
        return float(cfg["angular_jitter_rad"])
    if "angular_jitter_deg" in cfg:
        return radians(float(cfg["angular_jitter_deg"]))
    return radians(2.0)


def _resolve_radius_range(cfg: Mapping[str, Any], wafer_radius_mm: float) -> tuple[float, float]:
    if "r_min_mm" in cfg:
        r_min = float(cfg["r_min_mm"])
    else:
        r_min = float(cfg.get("r_min_ratio", 0.0)) * wafer_radius_mm
    if "r_max_mm" in cfg:
        r_max = float(cfg["r_max_mm"])
    else:
        r_max = float(cfg.get("r_max_ratio", 1.0)) * wafer_radius_mm
    r_max = min(r_max, wafer_radius_mm)
    if r_min < 0.0 or r_max <= 0.0 or r_min >= r_max:
        raise ValueError("invalid radius range")
    return r_min, r_max


def _ensure_iterable(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return [value]
