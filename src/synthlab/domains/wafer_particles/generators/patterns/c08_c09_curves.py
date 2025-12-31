from __future__ import annotations

from math import radians, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm, resolve_width_norm
from .geometry import sample_arc_band, sample_spiral


@register_pattern("wafer_particles.pattern.C08_CurvedScratch")
class C08CurvedScratch(PatternBase):
    pattern_id = "C08_CurvedScratch"
    tags = ("scratch", "curved")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        arc_radius_norm = _resolve_arc_radius_norm(params, ctx)
        span_rad = _resolve_span_rad(params)
        width_norm = resolve_width_norm(params, ctx, default_ratio=0.02)
        angle_center = _resolve_angle_center_rad(params, rng)

        if arc_radius_norm <= 0:
            raise ValueError("arc_radius_norm must be positive")
        if span_rad <= 0:
            raise ValueError("span_rad must be positive")
        if width_norm <= 0:
            raise ValueError("width_norm must be positive")

        points = sample_arc_band(
            rng,
            ctx.n_particles,
            radius_norm=arc_radius_norm,
            angle_center=angle_center,
            angle_width=span_rad,
            radial_width=width_norm,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


@register_pattern("wafer_particles.pattern.C09_Spiral")
class C09Spiral(PatternBase):
    pattern_id = "C09_Spiral"
    tags = ("spiral",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        theta_max = _resolve_theta_max(params)
        start_r_norm = _resolve_radius_norm(params, ctx, "start_r_norm", "start_r_ratio", "start_r_mm", 0.1)
        end_r_norm = _resolve_radius_norm(params, ctx, "end_r_norm", "end_r_ratio", "end_r_mm", 1.0)
        width_norm = resolve_width_norm(params, ctx, default_ratio=0.02)

        if theta_max <= 0:
            raise ValueError("theta_max must be positive")
        if start_r_norm < 0 or end_r_norm > 1.0 or start_r_norm >= end_r_norm:
            raise ValueError("invalid spiral radius bounds")

        turns = theta_max / tau
        points = sample_spiral(
            rng,
            ctx.n_particles,
            start_r_norm=start_r_norm,
            end_r_norm=end_r_norm,
            turns=turns,
            width_norm=width_norm,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_angle_center_rad(cfg: Mapping[str, Any], rng: Any) -> float:
    if "angle_center_rad" in cfg:
        return float(cfg["angle_center_rad"])
    if "angle_center_deg" in cfg:
        return radians(float(cfg["angle_center_deg"]))
    if str(cfg.get("angle_center", "")).lower() == "random":
        return rng.random() * tau
    return 0.0


def _resolve_arc_radius_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "arc_radius_norm" in cfg:
        return float(cfg["arc_radius_norm"])
    if "arc_radius_mm" in cfg:
        return mm_to_norm(float(cfg["arc_radius_mm"]), ctx.wafer_radius_mm)
    return float(cfg.get("arc_radius_ratio", 0.7))


def _resolve_span_rad(cfg: Mapping[str, Any]) -> float:
    if "span_rad" in cfg:
        return float(cfg["span_rad"])
    if "span_deg" in cfg:
        return radians(float(cfg["span_deg"]))
    return radians(90.0)


def _resolve_theta_max(cfg: Mapping[str, Any]) -> float:
    if "theta_max" in cfg:
        return float(cfg["theta_max"])
    if "theta_max_deg" in cfg:
        return radians(float(cfg["theta_max_deg"]))
    if "turns" in cfg:
        return float(cfg["turns"]) * tau
    return 2.0 * tau


def _resolve_radius_norm(
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
    return float(cfg.get(ratio_key, default_ratio))
