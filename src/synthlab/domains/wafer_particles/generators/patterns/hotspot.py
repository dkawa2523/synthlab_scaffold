from __future__ import annotations

from math import cos, radians, sin, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm
from .geometry import sample_hotspot


@register_pattern("wafer_particles.pattern.hotspot")
class Hotspot(PatternBase):
    pattern_id = "wafer_particles.pattern.hotspot"
    tags = ("hotspot",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        sigma_norm = _resolve_sigma_norm(params, ctx)
        center_x, center_y = _resolve_center(params, rng, ctx)
        sigma_y_norm = None
        if "sigma_y_ratio" in params or "sigma_y_mm" in params or "sigma_y_norm" in params:
            sigma_y_norm = _resolve_sigma_norm(params, ctx, key_prefix="sigma_y")
        rotation = float(params.get("rotation_rad", 0.0))
        points = sample_hotspot(
            rng,
            ctx.n_particles,
            center_x=center_x,
            center_y=center_y,
            sigma_x=sigma_norm,
            sigma_y=sigma_y_norm,
            rotation_rad=rotation,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_sigma_norm(cfg: Mapping[str, Any], ctx: PatternContext, *, key_prefix: str = "sigma") -> float:
    key_norm = f"{key_prefix}_norm"
    key_mm = f"{key_prefix}_mm"
    key_ratio = f"{key_prefix}_ratio"
    if key_norm in cfg:
        sigma_norm = float(cfg[key_norm])
    elif key_mm in cfg:
        sigma_norm = mm_to_norm(float(cfg[key_mm]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get(key_ratio, 0.05))
        sigma_norm = ratio
    if sigma_norm <= 0:
        raise ValueError(f"{key_prefix} must be positive")
    return sigma_norm


def _resolve_center(cfg: Mapping[str, Any], rng: Any, ctx: PatternContext) -> tuple[float, float]:
    mode = str(cfg.get("mode", "center")).lower()
    if mode == "center":
        return 0.0, 0.0

    angle = _resolve_angle_rad(cfg, rng)
    if angle is None:
        angle = rng.random() * tau
    if mode == "edge":
        radius = float(cfg.get("center_radius_ratio", 0.9))
    elif mode == "random":
        if "center_radius_ratio" in cfg:
            radius = float(cfg["center_radius_ratio"])
        else:
            radius = rng.random() ** 0.5
    else:
        raise ValueError(f"unknown hotspot mode: {mode}")

    radius = max(0.0, min(radius, 1.0))
    return radius * cos(angle), radius * sin(angle)


def _resolve_angle_rad(cfg: Mapping[str, Any], rng: Any) -> float | None:
    if "center_angle_rad" in cfg:
        return float(cfg["center_angle_rad"])
    if "center_angle_deg" in cfg:
        return radians(float(cfg["center_angle_deg"]))
    if str(cfg.get("center_angle", "")) == "random":
        return rng.random() * tau
    return None
