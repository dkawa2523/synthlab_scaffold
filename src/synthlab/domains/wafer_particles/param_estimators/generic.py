from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_param_estimator


@register_param_estimator("wafer_particles.param_estimator.generic")
def estimate(cfg: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    stats = payload.get("stats")
    if not isinstance(stats, Mapping):
        return {}
    return {
        "r_mean_mm": stats.get("r_mean_mm"),
        "r_std_mm": stats.get("r_std_mm"),
        "r_mean_ratio": stats.get("r_mean_ratio"),
        "r_std_ratio": stats.get("r_std_ratio"),
        "theta_mean_rad": stats.get("theta_mean_rad"),
        "theta_std_rad": stats.get("theta_std_rad"),
        "theta_coverage": stats.get("theta_coverage"),
        "theta_span_rad": stats.get("theta_span_rad"),
        "x_mean_mm": stats.get("x_mean_mm"),
        "y_mean_mm": stats.get("y_mean_mm"),
    }
