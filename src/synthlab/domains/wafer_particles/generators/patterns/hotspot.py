from __future__ import annotations

from math import cos, radians, sin, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import build_particle, cartesian_to_polar_mm, resolve_sample_ctx


@register_pattern("wafer_particles.pattern.hotspot")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    sigma_mm = _resolve_sigma_mm(cfg, ctx.wafer_radius_mm)
    center_x_mm, center_y_mm = _resolve_center(cfg, rng, ctx.wafer_radius_mm)

    particles: list[dict[str, float | str]] = []
    max_attempts = ctx.n_particles * 20
    attempts = 0
    while len(particles) < ctx.n_particles and attempts < max_attempts:
        attempts += 1
        x_mm = center_x_mm + rng.gauss(0.0, sigma_mm)
        y_mm = center_y_mm + rng.gauss(0.0, sigma_mm)
        r_mm, theta_rad = cartesian_to_polar_mm(x_mm, y_mm)
        if r_mm <= ctx.wafer_radius_mm:
            particles.append(build_particle(r_mm, theta_rad))

    while len(particles) < ctx.n_particles:
        angle = rng.random() * tau
        r_mm = min(ctx.wafer_radius_mm, abs(rng.gauss(0.0, sigma_mm)))
        particles.append(build_particle(r_mm, angle))

    return particles


def _resolve_sigma_mm(cfg: Mapping[str, Any], wafer_radius_mm: float) -> float:
    if "sigma_mm" in cfg:
        sigma_mm = float(cfg["sigma_mm"])
    else:
        ratio = float(cfg.get("sigma_ratio", 0.05))
        sigma_mm = ratio * wafer_radius_mm
    if sigma_mm <= 0:
        raise ValueError("sigma_mm must be positive")
    return sigma_mm


def _resolve_center(cfg: Mapping[str, Any], rng: Any, wafer_radius_mm: float) -> tuple[float, float]:
    mode = str(cfg.get("mode", "center")).lower()
    if mode == "center":
        return 0.0, 0.0

    angle = _resolve_angle_rad(cfg, rng)
    if angle is None:
        angle = rng.random() * tau
    if mode == "edge":
        radius = float(cfg.get("center_radius_ratio", 0.9)) * wafer_radius_mm
    elif mode == "random":
        if "center_radius_ratio" in cfg:
            radius = float(cfg["center_radius_ratio"]) * wafer_radius_mm
        else:
            radius = wafer_radius_mm * (rng.random() ** 0.5)
    else:
        raise ValueError(f"unknown hotspot mode: {mode}")

    return radius * cos(angle), radius * sin(angle)


def _resolve_angle_rad(cfg: Mapping[str, Any], rng: Any) -> float | None:
    if "center_angle_rad" in cfg:
        return float(cfg["center_angle_rad"])
    if "center_angle_deg" in cfg:
        return radians(float(cfg["center_angle_deg"]))
    if str(cfg.get("center_angle", "")) == "random":
        return rng.random() * tau
    return None
