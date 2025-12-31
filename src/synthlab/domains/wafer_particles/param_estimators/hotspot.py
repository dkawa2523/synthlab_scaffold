from __future__ import annotations

from math import atan2, sqrt
from typing import Any, Mapping

from synthlab.framework.registry import register_param_estimator

from .common import mean, wrap_angle_rad


@register_param_estimator("wafer_particles.param_estimator.hotspot")
def estimate(cfg: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    points = payload.get("points_xy")
    if not isinstance(points, list) or not points:
        return {}
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    center_x = mean(xs)
    center_y = mean(ys)
    if center_x is None or center_y is None:
        return {}
    dist_sq = [(x - center_x) ** 2 + (y - center_y) ** 2 for x, y in points]
    dist_sq_mean = mean(dist_sq)
    sigma_mm = None
    if dist_sq_mean is not None:
        sigma_mm = sqrt(dist_sq_mean / 2.0)
    center_r = sqrt(center_x**2 + center_y**2)
    center_theta = wrap_angle_rad(atan2(center_y, center_x)) if center_r > 0 else 0.0
    return {
        "center_x_mm": center_x,
        "center_y_mm": center_y,
        "center_r_mm": center_r,
        "center_theta_rad": center_theta,
        "sigma_mm": sigma_mm,
    }
