from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_param_estimator


@register_param_estimator("wafer_particles.param_estimator.sector")
def estimate(cfg: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    stats = payload.get("stats")
    if not isinstance(stats, Mapping):
        return {}
    theta_center = stats.get("theta_mean_rad")
    theta_span = stats.get("theta_span_rad")
    span_quantile = stats.get("theta_span_quantile")
    angle_width = None
    if theta_span is not None:
        if span_quantile:
            angle_width = float(theta_span) / float(span_quantile)
        else:
            angle_width = float(theta_span)
    r_quantiles = stats.get("r_quantiles")
    r_p05 = None
    if isinstance(r_quantiles, Mapping) and r_quantiles.get("p05") is not None:
        r_p05 = float(r_quantiles["p05"])
    wafer_radius_mm = payload.get("wafer_radius_mm")
    edge_width_mm = None
    if wafer_radius_mm is not None and r_p05 is not None:
        edge_width_mm = float(wafer_radius_mm) - r_p05
    return {
        "angle_center_rad": theta_center,
        "angle_width_rad": angle_width,
        "edge_width_mm": edge_width_mm,
        "r_mean_ratio": stats.get("r_mean_ratio"),
        "theta_coverage": stats.get("theta_coverage"),
    }
