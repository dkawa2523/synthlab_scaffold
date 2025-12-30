from __future__ import annotations

from math import cos, radians, sin
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import build_particle, cartesian_to_polar_mm, resolve_sample_ctx

_ANGLE_CATEGORIES = {
    "horizontal": 0.0,
    "vertical": 1.5707963267948966,
    "diagonal": 0.7853981633974483,
    "diagonal_rev": 2.356194490192345,
}


@register_pattern("wafer_particles.pattern.scratch")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    angle_rad = _resolve_angle_rad(cfg)
    length_mm = _resolve_length_mm(cfg, ctx.wafer_radius_mm)
    width_mm = _resolve_width_mm(cfg, ctx.wafer_radius_mm)
    offset_mm = _resolve_offset_mm(cfg, ctx.wafer_radius_mm)

    dir_x = cos(angle_rad)
    dir_y = sin(angle_rad)
    perp_x = -dir_y
    perp_y = dir_x

    particles: list[dict[str, float | str]] = []
    max_attempts = ctx.n_particles * 20
    attempts = 0
    while len(particles) < ctx.n_particles and attempts < max_attempts:
        attempts += 1
        t = (rng.random() - 0.5) * length_mm
        jitter = (rng.random() - 0.5) * width_mm
        x_mm = dir_x * t + perp_x * (offset_mm + jitter)
        y_mm = dir_y * t + perp_y * (offset_mm + jitter)
        r_mm, theta_rad = cartesian_to_polar_mm(x_mm, y_mm)
        if r_mm <= ctx.wafer_radius_mm:
            particles.append(build_particle(r_mm, theta_rad))

    while len(particles) < ctx.n_particles:
        t = (rng.random() - 0.5) * length_mm
        x_mm = dir_x * t + perp_x * offset_mm
        y_mm = dir_y * t + perp_y * offset_mm
        r_mm, theta_rad = cartesian_to_polar_mm(x_mm, y_mm)
        if r_mm > ctx.wafer_radius_mm:
            r_mm = ctx.wafer_radius_mm
        particles.append(build_particle(r_mm, theta_rad))

    return particles


def _resolve_angle_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_rad" in cfg:
        return float(cfg["angle_rad"])
    if "angle_deg" in cfg:
        return radians(float(cfg["angle_deg"]))
    category = str(cfg.get("angle_category", "horizontal")).lower()
    return _ANGLE_CATEGORIES.get(category, 0.0)


def _resolve_length_mm(cfg: Mapping[str, Any], wafer_radius_mm: float) -> float:
    if "length_mm" in cfg:
        length_mm = float(cfg["length_mm"])
    else:
        ratio = float(cfg.get("length_ratio", 1.0))
        length_mm = ratio * wafer_radius_mm * 2.0
    if length_mm <= 0:
        raise ValueError("length_mm must be positive")
    return length_mm


def _resolve_width_mm(cfg: Mapping[str, Any], wafer_radius_mm: float) -> float:
    if "width_mm" in cfg:
        width_mm = float(cfg["width_mm"])
    else:
        ratio = float(cfg.get("width_ratio", 0.01))
        width_mm = ratio * wafer_radius_mm
    if width_mm <= 0:
        raise ValueError("width_mm must be positive")
    return width_mm


def _resolve_offset_mm(cfg: Mapping[str, Any], wafer_radius_mm: float) -> float:
    if "offset_mm" in cfg:
        offset_mm = float(cfg["offset_mm"])
    else:
        ratio = float(cfg.get("offset_ratio", 0.0))
        offset_mm = ratio * wafer_radius_mm
    return offset_mm
