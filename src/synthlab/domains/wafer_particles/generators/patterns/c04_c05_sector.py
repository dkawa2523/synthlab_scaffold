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


@register_pattern("wafer_particles.pattern.C04_Sector_Edge")
class C04SectorEdge(PatternBase):
    pattern_id = "C04_Sector_Edge"
    touch_edge = True
    tags = ("sector", "edge")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        center_rad = _resolve_angle_center_rad(params, rng)
        width_rad = _resolve_angle_width_rad(params)
        edge_width_norm = _resolve_edge_width_norm(params, ctx)
        radial_beta = _resolve_radial_beta(params)
        kappa = _resolve_theta_kappa(params)

        if edge_width_norm <= 0:
            raise ValueError("edge_width must be positive")
        if edge_width_norm > 1.0:
            raise ValueError("edge_width must be <= 1.0")
        r_inner = max(0.0, 1.0 - edge_width_norm)

        points = sample_sector(
            rng,
            ctx.n_particles,
            theta_center=center_rad,
            theta_width=width_rad,
            r_inner=r_inner,
            r_outer=1.0,
            radial_beta=radial_beta,
            theta_vonmises_kappa=kappa,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


@register_pattern("wafer_particles.pattern.C05_Sector_Internal")
class C05SectorInternal(PatternBase):
    pattern_id = "C05_Sector_Internal"
    internal_only = True
    tags = ("sector", "internal")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        center_rad = _resolve_angle_center_rad(params, rng)
        width_rad = _resolve_angle_width_rad(params)
        r_inner, r_outer = _resolve_radius_bounds(params, ctx)
        edge_margin = _resolve_edge_margin_norm(params, ctx)
        radial_beta = _resolve_radial_beta(params)
        kappa = _resolve_theta_kappa(params)

        if r_outer > 1.0 - edge_margin:
            raise ValueError("sector internal r_outer exceeds edge margin")

        points = sample_sector(
            rng,
            ctx.n_particles,
            theta_center=center_rad,
            theta_width=width_rad,
            r_inner=r_inner,
            r_outer=r_outer,
            radial_beta=radial_beta,
            theta_vonmises_kappa=kappa,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_angle_center_rad(cfg: Mapping[str, Any], rng: Any) -> float:
    if "angle_center_rad" in cfg:
        return float(cfg["angle_center_rad"])
    if "angle_center_deg" in cfg:
        return radians(float(cfg["angle_center_deg"]))
    side = str(cfg.get("side", "")).lower()
    if side in _SIDE_TO_CENTER_RAD:
        return _SIDE_TO_CENTER_RAD[side]
    if str(cfg.get("angle_center", "")).lower() == "random":
        return rng.random() * tau
    if str(cfg.get("center_angle", "")).lower() == "random":
        return rng.random() * tau
    return 0.0


def _resolve_angle_width_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_width_rad" in cfg:
        return float(cfg["angle_width_rad"])
    if "angle_width_deg" in cfg:
        return radians(float(cfg["angle_width_deg"]))
    return radians(45.0)


def _resolve_edge_width_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "edge_width_norm" in cfg:
        return float(cfg["edge_width_norm"])
    if "edge_width_mm" in cfg:
        return mm_to_norm(float(cfg["edge_width_mm"]), ctx.wafer_radius_mm)
    return float(cfg.get("edge_width_ratio", 0.12))


def _resolve_radius_bounds(cfg: Mapping[str, Any], ctx: PatternContext) -> tuple[float, float]:
    r_inner = _resolve_norm(cfg, "r_inner_norm", "r_inner_ratio", "r_inner_mm", ctx, 0.2)
    r_outer = _resolve_norm(cfg, "r_outer_norm", "r_outer_ratio", "r_outer_mm", ctx, 0.8)
    if r_inner < 0 or r_outer > 1.0 or r_inner >= r_outer:
        raise ValueError("invalid radius bounds")
    return r_inner, r_outer


def _resolve_edge_margin_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "edge_margin_norm" in cfg:
        margin = float(cfg["edge_margin_norm"])
    elif "edge_margin_mm" in cfg:
        margin = mm_to_norm(float(cfg["edge_margin_mm"]), ctx.wafer_radius_mm)
    else:
        margin = float(cfg.get("edge_margin_ratio", 0.05))
    if margin < 0:
        raise ValueError("edge_margin must be non-negative")
    return margin


def _resolve_norm(
    cfg: Mapping[str, Any],
    norm_key: str,
    ratio_key: str,
    mm_key: str,
    ctx: PatternContext,
    default_ratio: float,
) -> float:
    if norm_key in cfg:
        value = float(cfg[norm_key])
    elif mm_key in cfg:
        value = mm_to_norm(float(cfg[mm_key]), ctx.wafer_radius_mm)
    else:
        value = float(cfg.get(ratio_key, default_ratio))
    return float(value)


def _resolve_radial_beta(cfg: Mapping[str, Any]) -> tuple[float, float] | None:
    if "radial_beta" in cfg:
        value = cfg["radial_beta"]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("radial_beta must be a 2-item sequence")
        alpha, beta = float(value[0]), float(value[1])
        if alpha <= 0 or beta <= 0:
            raise ValueError("radial_beta must be positive")
        return alpha, beta
    alpha = cfg.get("radial_beta_alpha")
    beta = cfg.get("radial_beta_beta")
    if alpha is None and beta is None:
        return None
    if alpha is None or beta is None:
        raise ValueError("radial_beta requires alpha and beta")
    alpha_val = float(alpha)
    beta_val = float(beta)
    if alpha_val <= 0 or beta_val <= 0:
        raise ValueError("radial_beta must be positive")
    return alpha_val, beta_val


def _resolve_theta_kappa(cfg: Mapping[str, Any]) -> float | None:
    if "theta_vonmises_kappa" in cfg:
        return float(cfg["theta_vonmises_kappa"])
    if "angle_vonmises_kappa" in cfg:
        return float(cfg["angle_vonmises_kappa"])
    return None
