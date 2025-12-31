from __future__ import annotations

import math
from typing import Callable, Iterable


def mask_annulus(r_norm: float, *, r_inner: float, r_outer: float) -> bool:
    r_inner = max(0.0, float(r_inner))
    r_outer = max(0.0, float(r_outer))
    if r_outer < r_inner:
        r_inner, r_outer = r_outer, r_inner
    return r_inner <= r_norm <= r_outer


def mask_arc_band(
    r_norm: float,
    theta_rad: float,
    *,
    r_inner: float,
    r_outer: float,
    theta_center: float,
    theta_width: float,
) -> bool:
    if not mask_annulus(r_norm, r_inner=r_inner, r_outer=r_outer):
        return False
    half_width = max(0.0, float(theta_width)) * 0.5
    theta = _normalize_theta(theta_rad)
    center = _normalize_theta(theta_center)
    return _angle_in_range(theta, center - half_width, center + half_width)


def mask_ring_segment(
    r_norm: float,
    theta_rad: float,
    *,
    r_inner: float,
    r_outer: float,
    theta_start: float,
    theta_end: float,
) -> bool:
    if not mask_annulus(r_norm, r_inner=r_inner, r_outer=r_outer):
        return False
    theta = _normalize_theta(theta_rad)
    return _angle_in_range(theta, theta_start, theta_end)


def crescent_region(
    x_norm: float,
    y_norm: float,
    *,
    outer_radius: float = 1.0,
    inner_radius: float = 0.7,
    offset_x: float = 0.2,
    offset_y: float = 0.0,
    mode: str = "edge",
) -> bool:
    outer_radius = max(0.0, float(outer_radius))
    inner_radius = max(0.0, float(inner_radius))
    in_outer = math.hypot(x_norm, y_norm) <= outer_radius
    in_inner = math.hypot(x_norm - offset_x, y_norm - offset_y) <= inner_radius
    mode = str(mode).lower()
    if mode == "edge":
        return in_outer and not in_inner
    if mode == "internal":
        return in_inner and not in_outer
    raise ValueError(f"unknown crescent mode: {mode}")


def apply_mask(
    points: Iterable[tuple[float, float]],
    mask_fn: Callable[[float, float], bool],
) -> list[tuple[float, float]]:
    return [(r, theta) for r, theta in points if mask_fn(r, theta)]


def _normalize_theta(theta_rad: float) -> float:
    return float(theta_rad) % math.tau


def _angle_in_range(theta: float, start: float, end: float) -> bool:
    start = _normalize_theta(start)
    end = _normalize_theta(end)
    if start <= end:
        return start <= theta <= end
    return theta >= start or theta <= end
