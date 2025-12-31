from __future__ import annotations

from math import radians, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm
from .geometry import sample_edge_spray


@register_pattern("wafer_particles.pattern.C14_EdgeSource_Spray")
class C14EdgeSourceSpray(PatternBase):
    pattern_id = "C14_EdgeSource_Spray"
    touch_edge = True
    tags = ("edge", "spray")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        angle_center = _resolve_angle_center_rad(params, rng)
        angle_width = _resolve_angle_width_rad(params)
        radial_scale = _resolve_radial_scale_norm(params, ctx)
        bursts = int(params.get("bursts", 1))
        if bursts != 1:
            raise ValueError("C14_EdgeSource_Spray requires bursts=1")

        points = sample_edge_spray(
            rng,
            ctx.n_particles,
            angle_center=angle_center,
            angle_width=angle_width,
            radial_scale=radial_scale,
            bursts=1,
            burst_angle_jitter=_resolve_burst_jitter_rad(params),
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


@register_pattern("wafer_particles.pattern.C15_EdgeSource_Bursty")
class C15EdgeSourceBursty(PatternBase):
    pattern_id = "C15_EdgeSource_Bursty"
    touch_edge = True
    tags = ("edge", "spray", "bursty")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        angle_center = _resolve_angle_center_rad(params, rng)
        angle_width = _resolve_angle_width_rad(params)
        radial_scale = _resolve_radial_scale_norm(params, ctx)
        bursts = int(params.get("bursts", 3))
        if bursts < 2:
            raise ValueError("C15_EdgeSource_Bursty requires bursts >= 2")

        points = sample_edge_spray(
            rng,
            ctx.n_particles,
            angle_center=angle_center,
            angle_width=angle_width,
            radial_scale=radial_scale,
            bursts=bursts,
            burst_angle_jitter=_resolve_burst_jitter_rad(params),
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_angle_center_rad(cfg: Mapping[str, Any], rng: Any) -> float | None:
    if "angle_center_rad" in cfg:
        return float(cfg["angle_center_rad"])
    if "angle_center_deg" in cfg:
        return radians(float(cfg["angle_center_deg"]))
    if str(cfg.get("angle_center", "")).lower() == "random":
        return rng.random() * tau
    return None


def _resolve_angle_width_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_width_rad" in cfg:
        return float(cfg["angle_width_rad"])
    if "angle_width_deg" in cfg:
        return radians(float(cfg["angle_width_deg"]))
    return radians(15.0)


def _resolve_radial_scale_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "radial_scale_norm" in cfg:
        value = float(cfg["radial_scale_norm"])
    elif "radial_scale_mm" in cfg:
        value = mm_to_norm(float(cfg["radial_scale_mm"]), ctx.wafer_radius_mm)
    else:
        value = float(cfg.get("radial_scale_ratio", 0.05))
    if value < 0:
        raise ValueError("radial_scale must be non-negative")
    return value


def _resolve_burst_jitter_rad(cfg: Mapping[str, Any]) -> float:
    if "burst_angle_jitter_rad" in cfg:
        return float(cfg["burst_angle_jitter_rad"])
    if "burst_angle_jitter_deg" in cfg:
        return radians(float(cfg["burst_angle_jitter_deg"]))
    return radians(4.0)
