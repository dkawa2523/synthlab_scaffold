from __future__ import annotations

from math import radians, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm
from .geometry import sample_sector

_SIDE_TO_CENTER_RAD = {
    "right": 0.0,
    "top": tau / 4.0,
    "left": tau / 2.0,
    "bottom": 3.0 * tau / 4.0,
}


@register_pattern("wafer_particles.pattern.edge_sector")
class EdgeSector(PatternBase):
    pattern_id = "wafer_particles.pattern.edge_sector"
    touch_edge = True
    tags = ("edge", "sector")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        center_rad = _resolve_angle_center_rad(params)
        width_rad = _resolve_angle_width_rad(params)
        edge_width_norm = _resolve_edge_width_norm(params, ctx)

        r_inner = max(0.0, 1.0 - edge_width_norm)
        points = sample_sector(
            rng,
            ctx.n_particles,
            theta_center=center_rad,
            theta_width=width_rad,
            r_inner=r_inner,
            r_outer=1.0,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_angle_center_rad(cfg: Mapping[str, Any]) -> float:
    mode = str(cfg.get("mode", "")).lower()
    side = str(cfg.get("side", "right")).lower()
    if mode == "custom" or side == "custom":
        if "angle_center_rad" in cfg:
            return float(cfg["angle_center_rad"])
        if "angle_center_deg" in cfg:
            return radians(float(cfg["angle_center_deg"]))
        raise ValueError("custom edge_sector requires angle_center_rad or angle_center_deg")
    if "angle_center_rad" in cfg:
        return float(cfg["angle_center_rad"])
    if "angle_center_deg" in cfg:
        return radians(float(cfg["angle_center_deg"]))
    return _SIDE_TO_CENTER_RAD.get(side, 0.0)


def _resolve_angle_width_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_width_rad" in cfg:
        return float(cfg["angle_width_rad"])
    if "angle_width_deg" in cfg:
        return radians(float(cfg["angle_width_deg"]))
    return radians(40.0)


def _resolve_edge_width_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "edge_width_norm" in cfg:
        width_norm = float(cfg["edge_width_norm"])
    elif "edge_width_mm" in cfg:
        width_norm = mm_to_norm(float(cfg["edge_width_mm"]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get("edge_width_ratio", 0.1))
        width_norm = ratio
    if width_norm <= 0:
        raise ValueError("edge_width must be positive")
    return min(width_norm, 1.0)
