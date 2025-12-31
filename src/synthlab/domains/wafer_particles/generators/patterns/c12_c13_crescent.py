from __future__ import annotations

from math import cos, sin, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, cartesian_to_polar_norm, mm_to_norm, sample_uniform_disk_xy


@register_pattern("wafer_particles.pattern.C12_Crescent_Edge")
class C12CrescentEdge(PatternBase):
    pattern_id = "C12_Crescent_Edge"
    touch_edge = True
    tags = ("crescent", "edge")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        outer_radius = _resolve_outer_radius_norm(params, ctx, default_ratio=1.0)
        inner_radius = _resolve_inner_radius_norm(params, ctx, outer_radius, default_ratio=0.7)
        offset_norm = _resolve_offset_norm(params, ctx, outer_radius, default_ratio=0.3)
        edge_margin = _resolve_edge_margin_norm(params, ctx, default_ratio=0.02)
        angle_center = _resolve_angle_center_rad(params, rng)

        _validate_crescent_params(outer_radius, inner_radius, offset_norm)
        if outer_radius < 1.0 - edge_margin:
            raise ValueError("crescent edge outer_radius does not reach edge margin")

        points = _sample_crescent(
            rng,
            ctx.n_particles,
            outer_radius=outer_radius,
            inner_radius=inner_radius,
            offset_norm=offset_norm,
            angle_center=angle_center,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


@register_pattern("wafer_particles.pattern.C13_Crescent_Internal")
class C13CrescentInternal(PatternBase):
    pattern_id = "C13_Crescent_Internal"
    internal_only = True
    tags = ("crescent", "internal")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        outer_radius = _resolve_outer_radius_norm(params, ctx, default_ratio=0.7)
        inner_radius = _resolve_inner_radius_norm(params, ctx, outer_radius, default_ratio=0.55)
        offset_norm = _resolve_offset_norm(params, ctx, outer_radius, default_ratio=0.25)
        edge_margin = _resolve_edge_margin_norm(params, ctx, default_ratio=0.05)
        angle_center = _resolve_angle_center_rad(params, rng)

        _validate_crescent_params(outer_radius, inner_radius, offset_norm)
        if outer_radius > 1.0 - edge_margin:
            raise ValueError("crescent internal outer_radius exceeds edge margin")

        points = _sample_crescent(
            rng,
            ctx.n_particles,
            outer_radius=outer_radius,
            inner_radius=inner_radius,
            offset_norm=offset_norm,
            angle_center=angle_center,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_outer_radius_norm(cfg: Mapping[str, Any], ctx: PatternContext, *, default_ratio: float) -> float:
    if "outer_radius_norm" in cfg:
        value = float(cfg["outer_radius_norm"])
    elif "outer_radius_mm" in cfg:
        value = mm_to_norm(float(cfg["outer_radius_mm"]), ctx.wafer_radius_mm)
    else:
        value = float(cfg.get("outer_radius_ratio", default_ratio))
    return min(max(value, 0.0), 1.0)


def _resolve_inner_radius_norm(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    outer_radius: float,
    *,
    default_ratio: float,
) -> float:
    if "inner_radius_norm" in cfg:
        value = float(cfg["inner_radius_norm"])
    elif "inner_radius_mm" in cfg:
        value = mm_to_norm(float(cfg["inner_radius_mm"]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get("inner_radius_ratio", default_ratio))
        value = outer_radius * ratio
    return max(value, 0.0)


def _resolve_offset_norm(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    outer_radius: float,
    *,
    default_ratio: float,
) -> float:
    if "offset_norm" in cfg:
        value = float(cfg["offset_norm"])
    elif "offset_mm" in cfg:
        value = mm_to_norm(float(cfg["offset_mm"]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get("offset_ratio", default_ratio))
        value = outer_radius * ratio
    return max(value, 0.0)


def _resolve_edge_margin_norm(cfg: Mapping[str, Any], ctx: PatternContext, *, default_ratio: float) -> float:
    if "edge_margin_norm" in cfg:
        margin = float(cfg["edge_margin_norm"])
    elif "edge_margin_mm" in cfg:
        margin = mm_to_norm(float(cfg["edge_margin_mm"]), ctx.wafer_radius_mm)
    else:
        margin = float(cfg.get("edge_margin_ratio", default_ratio))
    if margin < 0:
        raise ValueError("edge_margin must be non-negative")
    return margin


def _resolve_angle_center_rad(cfg: Mapping[str, Any], rng: Any) -> float:
    if "angle_center_rad" in cfg:
        return float(cfg["angle_center_rad"])
    if "angle_center_deg" in cfg:
        return float(cfg["angle_center_deg"]) * tau / 360.0
    if str(cfg.get("angle_center", "")).lower() == "random":
        return rng.random() * tau
    return 0.0


def _validate_crescent_params(outer_radius: float, inner_radius: float, offset_norm: float) -> None:
    if outer_radius <= 0:
        raise ValueError("outer_radius must be positive")
    if inner_radius <= 0 or inner_radius >= outer_radius:
        raise ValueError("inner_radius must be in (0, outer_radius)")
    if offset_norm <= 0:
        raise ValueError("offset_norm must be positive")


def _sample_crescent(
    rng: Any,
    n: int,
    *,
    outer_radius: float,
    inner_radius: float,
    offset_norm: float,
    angle_center: float,
) -> list[tuple[float, float]]:
    offset_x = offset_norm * cos(angle_center)
    offset_y = offset_norm * sin(angle_center)
    inner_radius_sq = inner_radius * inner_radius
    out: list[tuple[float, float]] = []
    attempts = 0
    max_attempts = n * 80
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        x_unit, y_unit = sample_uniform_disk_xy(rng)
        x_norm = x_unit * outer_radius
        y_norm = y_unit * outer_radius
        dx = x_norm - offset_x
        dy = y_norm - offset_y
        if dx * dx + dy * dy <= inner_radius_sq:
            continue
        r_norm, theta_rad = cartesian_to_polar_norm(x_norm, y_norm)
        if r_norm <= 1.0:
            out.append((r_norm, theta_rad))
    if len(out) < n:
        raise ValueError("crescent sampling failed; region too small")
    return out
