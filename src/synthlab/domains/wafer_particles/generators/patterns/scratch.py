from __future__ import annotations

from math import cos, radians, sin
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm
from .geometry import sample_line_segment

_ANGLE_CATEGORIES = {
    "horizontal": 0.0,
    "vertical": 1.5707963267948966,
    "diagonal": 0.7853981633974483,
    "diagonal_rev": 2.356194490192345,
}


@register_pattern("wafer_particles.pattern.scratch")
class Scratch(PatternBase):
    pattern_id = "wafer_particles.pattern.scratch"
    tags = ("scratch", "line")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        angle_rad = _resolve_angle_rad(params)
        length_norm = _resolve_length_norm(params, ctx)
        width_norm = _resolve_width_norm(params, ctx)
        offset_norm = _resolve_offset_norm(params, ctx)

        perp_x = -sin(angle_rad)
        perp_y = cos(angle_rad)
        center_x = perp_x * offset_norm
        center_y = perp_y * offset_norm

        points = sample_line_segment(
            rng,
            ctx.n_particles,
            center_x=center_x,
            center_y=center_y,
            angle_rad=angle_rad,
            length_norm=length_norm,
            width_norm=width_norm,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_angle_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_rad" in cfg:
        return float(cfg["angle_rad"])
    if "angle_deg" in cfg:
        return radians(float(cfg["angle_deg"]))
    category = str(cfg.get("angle_category", "horizontal")).lower()
    return _ANGLE_CATEGORIES.get(category, 0.0)


def _resolve_length_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "length_norm" in cfg:
        length_norm = float(cfg["length_norm"])
    elif "length_mm" in cfg:
        length_norm = mm_to_norm(float(cfg["length_mm"]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get("length_ratio", 1.0))
        length_norm = ratio * 2.0
    if length_norm <= 0:
        raise ValueError("length must be positive")
    return float(length_norm)


def _resolve_width_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "width_norm" in cfg:
        width_norm = float(cfg["width_norm"])
    elif "width_mm" in cfg:
        width_norm = mm_to_norm(float(cfg["width_mm"]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get("width_ratio", 0.01))
        width_norm = ratio
    if width_norm <= 0:
        raise ValueError("width must be positive")
    return float(width_norm)


def _resolve_offset_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "offset_norm" in cfg:
        return float(cfg["offset_norm"])
    if "offset_mm" in cfg:
        return mm_to_norm(float(cfg["offset_mm"]), ctx.wafer_radius_mm)
    ratio = float(cfg.get("offset_ratio", 0.0))
    return ratio
