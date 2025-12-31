from __future__ import annotations

from math import cos, radians, sin, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm
from .geometry import sample_hotspot


@register_pattern("wafer_particles.pattern.C10_Hotspot_Iso")
class C10HotspotIso(PatternBase):
    pattern_id = "C10_Hotspot_Iso"
    tags = ("hotspot", "iso")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        sigma_norm = _resolve_sigma_norm(params, ctx, key_prefix="sigma")
        center_x, center_y = _resolve_center(params, rng, ctx)
        points = sample_hotspot(
            rng,
            ctx.n_particles,
            center_x=center_x,
            center_y=center_y,
            sigma_x=sigma_norm,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


@register_pattern("wafer_particles.pattern.C11_Hotspot_Elliptic")
class C11HotspotElliptic(PatternBase):
    pattern_id = "C11_Hotspot_Elliptic"
    tags = ("hotspot", "elliptic")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        sigma_x = _resolve_sigma_norm(params, ctx, key_prefix="sigma_x")
        sigma_y = _resolve_sigma_norm(params, ctx, key_prefix="sigma_y")
        if abs(sigma_x - sigma_y) < 1e-6:
            raise ValueError("sigma_x and sigma_y must differ for elliptic hotspot")
        rotation_rad = _resolve_rotation_rad(params)
        center_x, center_y = _resolve_center(params, rng, ctx)
        points = sample_hotspot(
            rng,
            ctx.n_particles,
            center_x=center_x,
            center_y=center_y,
            sigma_x=sigma_x,
            sigma_y=sigma_y,
            rotation_rad=rotation_rad,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_sigma_norm(cfg: Mapping[str, Any], ctx: PatternContext, *, key_prefix: str) -> float:
    key_norm = f"{key_prefix}_norm"
    key_mm = f"{key_prefix}_mm"
    key_ratio = f"{key_prefix}_ratio"
    if key_norm in cfg:
        sigma_norm = float(cfg[key_norm])
    elif key_mm in cfg:
        sigma_norm = mm_to_norm(float(cfg[key_mm]), ctx.wafer_radius_mm)
    else:
        sigma_norm = float(cfg.get(key_ratio, 0.05))
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


def _resolve_rotation_rad(cfg: Mapping[str, Any]) -> float:
    if "rotation_rad" in cfg:
        return float(cfg["rotation_rad"])
    if "rotation_deg" in cfg:
        return radians(float(cfg["rotation_deg"]))
    return 0.0
