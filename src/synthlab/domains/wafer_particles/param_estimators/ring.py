from __future__ import annotations

import math
from typing import Any, Mapping

from synthlab.framework.registry import register_param_estimator


@register_param_estimator("wafer_particles.param_estimator.ring")
def estimate(cfg: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    stats = payload.get("stats")
    if not isinstance(stats, Mapping):
        return {}
    r_mean = stats.get("r_mean_mm")
    r_std = stats.get("r_std_mm")
    width_scale = math.sqrt(12.0)
    if isinstance(cfg, Mapping) and cfg.get("width_scale") is not None:
        width_scale = float(cfg.get("width_scale"))
    width_mm = None
    if r_std is not None:
        width_mm = float(r_std) * width_scale
    return {
        "radius_mm": r_mean,
        "width_mm": width_mm,
        "r_mean_ratio": stats.get("r_mean_ratio"),
        "r_std_mm": r_std,
        "theta_coverage": stats.get("theta_coverage"),
    }
