from __future__ import annotations

from math import atan2, cos, sin, sqrt
from typing import Any, Mapping

from synthlab.framework.registry import register_param_estimator

from .common import mean, std, wrap_angle_rad


@register_param_estimator("wafer_particles.param_estimator.scratch")
def estimate(cfg: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    points = payload.get("points_xy")
    if not isinstance(points, list) or len(points) < 2:
        return {}
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    mean_x = mean(xs)
    mean_y = mean(ys)
    if mean_x is None or mean_y is None:
        return {}
    centered = [(x - mean_x, y - mean_y) for x, y in points]
    cov_xx = mean([dx * dx for dx, _ in centered]) or 0.0
    cov_yy = mean([dy * dy for _, dy in centered]) or 0.0
    cov_xy = mean([dx * dy for dx, dy in centered]) or 0.0
    angle = 0.5 * atan2(2.0 * cov_xy, cov_xx - cov_yy)
    dir_x = cos(angle)
    dir_y = sin(angle)
    perp_x = -dir_y
    perp_y = dir_x
    projections = [x * dir_x + y * dir_y for x, y in points]
    perp_proj = [x * perp_x + y * perp_y for x, y in points]
    offset_mm = mean(perp_proj)
    width_std = std(perp_proj, mean_value=offset_mm) if offset_mm is not None else None
    width_mm = None
    if width_std is not None:
        width_mm = width_std * sqrt(12.0)
    length_mm = None
    if projections:
        length_mm = max(projections) - min(projections)
    return {
        "angle_rad": wrap_angle_rad(angle),
        "width_mm": width_mm,
        "length_mm": length_mm,
        "offset_mm": offset_mm,
    }
