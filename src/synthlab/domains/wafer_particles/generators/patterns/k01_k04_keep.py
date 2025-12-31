from __future__ import annotations

from math import radians, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm, resolve_radius_norm, resolve_width_norm
from .geometry import sample_arc_band, sample_periodic_lines, sample_uniform_annulus

_ANGLE_CATEGORIES = {
    "horizontal": 0.0,
    "vertical": 1.5707963267948966,
    "diagonal": 0.7853981633974483,
    "diagonal_rev": 2.356194490192345,
}


@register_pattern("wafer_particles.pattern.K01_Donut_Hollow")
class K01DonutHollow(PatternBase):
    pattern_id = "K01_Donut_Hollow"
    tags = ("ring", "hollow")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        r_inner, r_outer = _resolve_annulus_bounds(
            params,
            ctx,
            default_radius_ratio=0.65,
            default_width_ratio=0.4,
            default_inner_ratio=0.35,
            default_outer_ratio=0.9,
        )
        points = sample_uniform_annulus(rng, ctx.n_particles, r_inner=r_inner, r_outer=r_outer)
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


@register_pattern("wafer_particles.pattern.K02_SemiRing_Segment")
class K02SemiRingSegment(PatternBase):
    pattern_id = "K02_SemiRing_Segment"
    tags = ("ring", "segment")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        arc_radius_norm = _resolve_arc_radius_norm(params, ctx, default_ratio=0.7)
        span_rad = _resolve_span_rad(params, default_deg=180.0)
        width_norm = resolve_width_norm(params, ctx, default_ratio=0.1)
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


@register_pattern("wafer_particles.pattern.K03_Edge_Arc")
class K03EdgeArc(PatternBase):
    pattern_id = "K03_Edge_Arc"
    touch_edge = True
    tags = ("edge", "arc")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        arc_radius_norm = _resolve_arc_radius_norm(params, ctx, default_ratio=0.95)
        span_rad = _resolve_span_rad(params, default_deg=70.0)
        width_norm = resolve_width_norm(params, ctx, default_ratio=0.06)
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


@register_pattern("wafer_particles.pattern.K04_Scratch_Periodic")
class K04ScratchPeriodic(PatternBase):
    pattern_id = "K04_Scratch_Periodic"
    tags = ("scratch", "periodic")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        angle_rad = _resolve_angle_rad(params)
        length_norm = _resolve_length_norm(params, ctx)
        width_norm = _resolve_line_width_norm(params, ctx)
        spacing_norm = _resolve_spacing_norm(params, ctx)
        n_lines = _resolve_n_lines(params)
        offset_norm = _resolve_offset_norm(params, ctx, spacing_norm, rng)

        if length_norm <= 0:
            raise ValueError("length must be positive")
        if width_norm <= 0:
            raise ValueError("width must be positive")
        if spacing_norm < 0:
            raise ValueError("spacing must be non-negative")
        if n_lines <= 0:
            raise ValueError("n_lines must be positive")
        if n_lines > 1 and spacing_norm <= 0:
            raise ValueError("spacing must be positive when n_lines > 1")

        points = sample_periodic_lines(
            rng,
            ctx.n_particles,
            angle_rad=angle_rad,
            length_norm=length_norm,
            width_norm=width_norm,
            spacing_norm=spacing_norm,
            n_lines=n_lines,
            offset_norm=offset_norm,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_annulus_bounds(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    *,
    default_radius_ratio: float,
    default_width_ratio: float,
    default_inner_ratio: float,
    default_outer_ratio: float,
) -> tuple[float, float]:
    has_direct = any(
        key in cfg
        for key in (
            "r_inner_norm",
            "r_inner_ratio",
            "r_inner_mm",
            "r_outer_norm",
            "r_outer_ratio",
            "r_outer_mm",
        )
    )
    if has_direct:
        r_inner = _resolve_norm(cfg, "r_inner_norm", "r_inner_ratio", "r_inner_mm", ctx, default_inner_ratio)
        r_outer = _resolve_norm(cfg, "r_outer_norm", "r_outer_ratio", "r_outer_mm", ctx, default_outer_ratio)
    else:
        radius_norm = resolve_radius_norm(cfg, ctx, default_ratio=default_radius_ratio)
        width_norm = resolve_width_norm(cfg, ctx, default_ratio=default_width_ratio)
        r_inner = radius_norm - width_norm * 0.5
        r_outer = radius_norm + width_norm * 0.5
    r_inner = max(0.0, min(float(r_inner), 1.0))
    r_outer = max(0.0, min(float(r_outer), 1.0))
    if r_inner >= r_outer:
        raise ValueError("invalid annulus bounds")
    return r_inner, r_outer


def _resolve_norm(
    cfg: Mapping[str, Any],
    norm_key: str,
    ratio_key: str,
    mm_key: str,
    ctx: PatternContext,
    default_ratio: float,
) -> float:
    if norm_key in cfg:
        return float(cfg[norm_key])
    if mm_key in cfg:
        return mm_to_norm(float(cfg[mm_key]), ctx.wafer_radius_mm)
    return float(cfg.get(ratio_key, default_ratio))


def _resolve_arc_radius_norm(cfg: Mapping[str, Any], ctx: PatternContext, *, default_ratio: float) -> float:
    if "arc_radius_norm" in cfg:
        return float(cfg["arc_radius_norm"])
    if "radius_norm" in cfg:
        return float(cfg["radius_norm"])
    if "arc_radius_mm" in cfg:
        return mm_to_norm(float(cfg["arc_radius_mm"]), ctx.wafer_radius_mm)
    if "radius_mm" in cfg:
        return mm_to_norm(float(cfg["radius_mm"]), ctx.wafer_radius_mm)
    if "arc_radius_ratio" in cfg:
        return float(cfg["arc_radius_ratio"])
    if "radius_ratio" in cfg:
        return float(cfg["radius_ratio"])
    return float(default_ratio)


def _resolve_angle_center_rad(cfg: Mapping[str, Any], rng: Any) -> float:
    if "angle_center_rad" in cfg:
        return float(cfg["angle_center_rad"])
    if "angle_center_deg" in cfg:
        return radians(float(cfg["angle_center_deg"]))
    center = cfg.get("angle_center")
    if isinstance(center, (int, float)):
        return float(center)
    if str(center).lower() == "random":
        return rng.random() * tau
    return 0.0


def _resolve_span_rad(cfg: Mapping[str, Any], *, default_deg: float) -> float:
    if "span_rad" in cfg:
        return float(cfg["span_rad"])
    if "span_deg" in cfg:
        return radians(float(cfg["span_deg"]))
    if "angle_width_rad" in cfg:
        return float(cfg["angle_width_rad"])
    if "angle_width_deg" in cfg:
        return radians(float(cfg["angle_width_deg"]))
    return radians(float(default_deg))


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
    return float(length_norm)


def _resolve_line_width_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "width_norm" in cfg:
        return float(cfg["width_norm"])
    if "width_mm" in cfg:
        return mm_to_norm(float(cfg["width_mm"]), ctx.wafer_radius_mm)
    return float(cfg.get("width_ratio", 0.01))


def _resolve_spacing_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "spacing_norm" in cfg:
        return float(cfg["spacing_norm"])
    if "spacing_mm" in cfg:
        return mm_to_norm(float(cfg["spacing_mm"]), ctx.wafer_radius_mm)
    return float(cfg.get("spacing_ratio", 0.12))


def _resolve_n_lines(cfg: Mapping[str, Any]) -> int:
    return int(cfg.get("n_lines", 4))


def _resolve_offset_norm(cfg: Mapping[str, Any], ctx: PatternContext, spacing_norm: float, rng: Any) -> float:
    if "offset_norm" in cfg:
        return float(cfg["offset_norm"])
    if "offset_mm" in cfg:
        return mm_to_norm(float(cfg["offset_mm"]), ctx.wafer_radius_mm)
    if "offset_ratio" in cfg:
        return float(cfg["offset_ratio"])
    mode = str(cfg.get("offset_mode", cfg.get("phase_mode", ""))).lower()
    if mode in {"random", "random_phase", "random_offset"} or bool(cfg.get("offset_random", False)) or bool(
        cfg.get("phase_random", False)
    ):
        if spacing_norm <= 0:
            return 0.0
        return (rng.random() - 0.5) * spacing_norm
    return 0.0
