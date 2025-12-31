from __future__ import annotations

import math
from typing import Any, Iterable


def polar_to_cartesian_norm(r_norm: float, theta_rad: float) -> tuple[float, float]:
    return r_norm * math.cos(theta_rad), r_norm * math.sin(theta_rad)


def cartesian_to_polar_norm(x_norm: float, y_norm: float) -> tuple[float, float]:
    r_norm = math.hypot(x_norm, y_norm)
    theta_rad = math.atan2(y_norm, x_norm) % math.tau
    return r_norm, theta_rad


def sample_uniform_disk(rng: Any, n: int) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    out: list[tuple[float, float]] = []
    for _ in range(n):
        r_norm = math.sqrt(rng.random())
        theta = rng.random() * math.tau
        out.append((r_norm, theta))
    return out


def sample_uniform_annulus(
    rng: Any,
    n: int,
    *,
    r_inner: float,
    r_outer: float,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    r_inner = _clamp_r_norm(r_inner)
    r_outer = _clamp_r_norm(r_outer)
    if r_outer < r_inner:
        r_inner, r_outer = r_outer, r_inner
    out: list[tuple[float, float]] = []
    r_inner_sq = r_inner * r_inner
    r_outer_sq = r_outer * r_outer
    span = r_outer_sq - r_inner_sq
    for _ in range(n):
        r_sq = r_inner_sq + rng.random() * span
        r_norm = math.sqrt(r_sq)
        theta = rng.random() * math.tau
        out.append((r_norm, theta))
    return out


def sample_sector(
    rng: Any,
    n: int,
    *,
    theta_center: float,
    theta_width: float,
    r_inner: float = 0.0,
    r_outer: float = 1.0,
    radial_beta: tuple[float, float] | None = None,
    theta_vonmises_kappa: float | None = None,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    r_inner = _clamp_r_norm(r_inner)
    r_outer = _clamp_r_norm(r_outer)
    if r_outer < r_inner:
        r_inner, r_outer = r_outer, r_inner
    theta_width = max(0.0, float(theta_width))
    out: list[tuple[float, float]] = []
    for _ in range(n):
        theta = _sample_theta_trunc_vonmises(rng, theta_center, theta_width, theta_vonmises_kappa)
        r_norm = _sample_radial(rng, r_inner, r_outer, radial_beta)
        out.append((r_norm, theta))
    return out


def sample_radial_lines(
    rng: Any,
    n: int,
    *,
    n_lines: int,
    length_norm: float,
    width_norm: float,
    angular_jitter_rad: float = 0.0,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    if n_lines <= 0:
        raise ValueError("n_lines must be positive")
    length_norm = max(0.0, float(length_norm))
    width_norm = max(0.0, float(width_norm))
    angles = [math.tau * idx / n_lines for idx in range(n_lines)]
    out: list[tuple[float, float]] = []
    max_attempts = n * 20
    attempts = 0
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        angle = angles[int(rng.random() * n_lines)]
        if angular_jitter_rad > 0:
            angle += rng.gauss(0.0, angular_jitter_rad)
        t = rng.random() * length_norm
        offset = (rng.random() - 0.5) * width_norm
        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        perp_x = -dir_y
        perp_y = dir_x
        x = dir_x * t + perp_x * offset
        y = dir_y * t + perp_y * offset
        r_norm, theta = cartesian_to_polar_norm(x, y)
        if r_norm <= 1.0:
            out.append((r_norm, theta))
    while len(out) < n:
        angle = angles[int(rng.random() * n_lines)]
        t = rng.random() * length_norm
        x = math.cos(angle) * t
        y = math.sin(angle) * t
        r_norm, theta = cartesian_to_polar_norm(x, y)
        out.append((_clamp_r_norm(r_norm), theta))
    return out


def sample_line_segment(
    rng: Any,
    n: int,
    *,
    center_x: float,
    center_y: float,
    angle_rad: float,
    length_norm: float,
    width_norm: float,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    length_norm = max(0.0, float(length_norm))
    width_norm = max(0.0, float(width_norm))
    dir_x = math.cos(angle_rad)
    dir_y = math.sin(angle_rad)
    perp_x = -dir_y
    perp_y = dir_x

    out: list[tuple[float, float]] = []
    max_attempts = n * 20
    attempts = 0
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        t = (rng.random() - 0.5) * length_norm
        offset = (rng.random() - 0.5) * width_norm
        x = center_x + dir_x * t + perp_x * offset
        y = center_y + dir_y * t + perp_y * offset
        r_norm, theta = cartesian_to_polar_norm(x, y)
        if r_norm <= 1.0:
            out.append((r_norm, theta))
    while len(out) < n:
        t = (rng.random() - 0.5) * length_norm
        x = center_x + dir_x * t
        y = center_y + dir_y * t
        r_norm, theta = cartesian_to_polar_norm(x, y)
        out.append((_clamp_r_norm(r_norm), theta))
    return out


def sample_periodic_lines(
    rng: Any,
    n: int,
    *,
    angle_rad: float,
    length_norm: float,
    width_norm: float,
    spacing_norm: float,
    n_lines: int,
    offset_norm: float = 0.0,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    if n_lines <= 0:
        raise ValueError("n_lines must be positive")
    if spacing_norm < 0:
        raise ValueError("spacing_norm must be non-negative")
    offsets = [
        offset_norm + (idx - (n_lines - 1) / 2.0) * spacing_norm
        for idx in range(n_lines)
    ]
    out: list[tuple[float, float]] = []
    max_attempts = n * 20
    attempts = 0
    dir_x = math.cos(angle_rad)
    dir_y = math.sin(angle_rad)
    perp_x = -dir_y
    perp_y = dir_x
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        offset = offsets[int(rng.random() * n_lines)]
        t = (rng.random() - 0.5) * length_norm
        jitter = (rng.random() - 0.5) * width_norm
        x = dir_x * t + perp_x * (offset + jitter)
        y = dir_y * t + perp_y * (offset + jitter)
        r_norm, theta = cartesian_to_polar_norm(x, y)
        if r_norm <= 1.0:
            out.append((r_norm, theta))
    while len(out) < n:
        offset = offsets[int(rng.random() * n_lines)]
        t = (rng.random() - 0.5) * length_norm
        x = dir_x * t + perp_x * offset
        y = dir_y * t + perp_y * offset
        r_norm, theta = cartesian_to_polar_norm(x, y)
        out.append((_clamp_r_norm(r_norm), theta))
    return out


def sample_arc_band(
    rng: Any,
    n: int,
    *,
    radius_norm: float,
    angle_center: float,
    angle_width: float,
    radial_width: float,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    radius_norm = _clamp_r_norm(radius_norm)
    radial_width = max(0.0, float(radial_width))
    r_min = _clamp_r_norm(radius_norm - radial_width * 0.5)
    r_max = _clamp_r_norm(radius_norm + radial_width * 0.5)
    out: list[tuple[float, float]] = []
    for _ in range(n):
        r_norm = rng.uniform(r_min, r_max)
        theta = angle_center + (rng.random() - 0.5) * angle_width
        out.append((r_norm, theta))
    return out


def sample_spiral(
    rng: Any,
    n: int,
    *,
    start_r_norm: float,
    end_r_norm: float,
    turns: float,
    width_norm: float = 0.0,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    start_r_norm = _clamp_r_norm(start_r_norm)
    end_r_norm = _clamp_r_norm(end_r_norm)
    turns = max(0.0, float(turns))
    width_norm = max(0.0, float(width_norm))
    out: list[tuple[float, float]] = []
    for _ in range(n):
        t = rng.random()
        theta = t * turns * math.tau
        r_norm = start_r_norm + t * (end_r_norm - start_r_norm)
        if width_norm > 0:
            r_norm += rng.gauss(0.0, width_norm)
        out.append((_clamp_r_norm(r_norm), theta % math.tau))
    return out


def sample_hotspot(
    rng: Any,
    n: int,
    *,
    center_x: float,
    center_y: float,
    sigma_x: float,
    sigma_y: float | None = None,
    rotation_rad: float = 0.0,
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    sigma_x = float(sigma_x)
    if sigma_x <= 0:
        raise ValueError("sigma_x must be positive")
    if sigma_y is None:
        sigma_y = sigma_x
    sigma_y = float(sigma_y)
    if sigma_y <= 0:
        raise ValueError("sigma_y must be positive")
    rot_cos = math.cos(rotation_rad)
    rot_sin = math.sin(rotation_rad)
    out: list[tuple[float, float]] = []
    max_attempts = n * 20
    attempts = 0
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        dx = rng.gauss(0.0, sigma_x)
        dy = rng.gauss(0.0, sigma_y)
        x = center_x + dx * rot_cos - dy * rot_sin
        y = center_y + dx * rot_sin + dy * rot_cos
        r_norm, theta = cartesian_to_polar_norm(x, y)
        if r_norm <= 1.0:
            out.append((r_norm, theta))
    while len(out) < n:
        angle = rng.random() * math.tau
        r_norm = _clamp_r_norm(abs(rng.gauss(0.0, max(sigma_x, sigma_y))))
        out.append((r_norm, angle))
    return out


def sample_edge_spray(
    rng: Any,
    n: int,
    *,
    angle_center: float | None = None,
    angle_width: float = math.radians(15.0),
    radial_scale: float = 0.05,
    bursts: int = 1,
    burst_angle_jitter: float = math.radians(4.0),
) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    if bursts <= 0:
        raise ValueError("bursts must be positive")
    radial_scale = max(0.0, float(radial_scale))
    if angle_center is None:
        angle_center = rng.random() * math.tau
    burst_centers = [
        angle_center + rng.gauss(0.0, burst_angle_jitter) for _ in range(bursts)
    ]
    out: list[tuple[float, float]] = []
    for _ in range(n):
        center = burst_centers[int(rng.random() * bursts)]
        theta = center + (rng.random() - 0.5) * angle_width
        if radial_scale > 0:
            inward = rng.expovariate(1.0 / radial_scale)
        else:
            inward = 0.0
        r_norm = _clamp_r_norm(1.0 - inward)
        out.append((r_norm, theta % math.tau))
    return out


def _clamp_r_norm(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def _sample_radial(
    rng: Any,
    r_inner: float,
    r_outer: float,
    radial_beta: tuple[float, float] | None,
) -> float:
    if radial_beta is None:
        r_inner_sq = r_inner * r_inner
        r_outer_sq = r_outer * r_outer
        span = r_outer_sq - r_inner_sq
        return math.sqrt(r_inner_sq + rng.random() * span)
    alpha, beta = radial_beta
    if alpha <= 0 or beta <= 0:
        raise ValueError("radial_beta must be positive")
    u = rng.betavariate(alpha, beta)
    return r_inner + u * (r_outer - r_inner)


def _sample_theta_trunc_vonmises(
    rng: Any,
    theta_center: float,
    theta_width: float,
    kappa: float | None,
) -> float:
    if not kappa or kappa <= 0 or theta_width <= 0:
        return theta_center + (rng.random() - 0.5) * theta_width
    max_log = kappa
    for _ in range(256):
        theta = theta_center + (rng.random() - 0.5) * theta_width
        log_p = kappa * math.cos(theta - theta_center)
        if rng.random() < math.exp(log_p - max_log):
            return theta
    return theta_center + (rng.random() - 0.5) * theta_width
