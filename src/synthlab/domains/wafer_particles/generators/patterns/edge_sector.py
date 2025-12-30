from __future__ import annotations

from math import radians, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import build_particle, resolve_sample_ctx

_SIDE_TO_CENTER_RAD = {
    "right": 0.0,
    "top": tau / 4.0,
    "left": tau / 2.0,
    "bottom": 3.0 * tau / 4.0,
}


@register_pattern("wafer_particles.pattern.edge_sector")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    center_rad = _resolve_angle_center_rad(cfg)
    width_rad = _resolve_angle_width_rad(cfg)
    edge_width_mm = _resolve_edge_width_mm(cfg, ctx.wafer_radius_mm)

    r_min = max(0.0, ctx.wafer_radius_mm - edge_width_mm)
    r_max = ctx.wafer_radius_mm

    particles: list[dict[str, float | str]] = []
    for _ in range(ctx.n_particles):
        r_mm = rng.uniform(r_min, r_max)
        theta_rad = center_rad + (rng.random() - 0.5) * width_rad
        particles.append(build_particle(r_mm, theta_rad))
    return particles


def _resolve_angle_center_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_center_rad" in cfg:
        return float(cfg["angle_center_rad"])
    if "angle_center_deg" in cfg:
        return radians(float(cfg["angle_center_deg"]))
    side = str(cfg.get("side", "right")).lower()
    return _SIDE_TO_CENTER_RAD.get(side, 0.0)


def _resolve_angle_width_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_width_rad" in cfg:
        return float(cfg["angle_width_rad"])
    if "angle_width_deg" in cfg:
        return radians(float(cfg["angle_width_deg"]))
    return radians(40.0)


def _resolve_edge_width_mm(cfg: Mapping[str, Any], wafer_radius_mm: float) -> float:
    if "edge_width_mm" in cfg:
        width_mm = float(cfg["edge_width_mm"])
    else:
        ratio = float(cfg.get("edge_width_ratio", 0.1))
        width_mm = ratio * wafer_radius_mm
    if width_mm <= 0:
        raise ValueError("edge_width_mm must be positive")
    return width_mm
