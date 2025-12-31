from __future__ import annotations

import math
from typing import Any, Iterable


def apply_position_jitter(
    particles: Iterable[dict[str, Any]],
    rng: Any,
    *,
    r_std_mm: float,
    theta_std_rad: float,
    wafer_radius_mm: float,
) -> None:
    if r_std_mm < 0:
        raise ValueError("jitter r_std_mm must be non-negative")
    if theta_std_rad < 0:
        raise ValueError("jitter theta_std_rad must be non-negative")
    if r_std_mm == 0.0 and theta_std_rad == 0.0:
        return
    for particle in particles:
        if r_std_mm > 0.0:
            r_mm = _resolve_r_mm(particle, wafer_radius_mm) + rng.gauss(0.0, r_std_mm)
            r_mm = _clamp(r_mm, 0.0, wafer_radius_mm)
            particle["r_mm"] = r_mm
            particle["r_norm"] = r_mm / wafer_radius_mm
        if theta_std_rad > 0.0:
            theta_rad = float(particle["theta_rad"]) + rng.gauss(0.0, theta_std_rad)
            particle["theta_rad"] = _normalize_theta(theta_rad)


def resolve_background_count(
    base_count: int,
    *,
    count: Any = None,
    fraction: Any = None,
) -> int:
    if base_count < 0:
        raise ValueError("base_count must be non-negative")
    if count is not None:
        try:
            parsed = int(count)
        except (TypeError, ValueError):
            raise ValueError("background count must be an int")
        if parsed < 0:
            raise ValueError("background count must be non-negative")
        return parsed
    if fraction is None:
        return 0
    try:
        ratio = float(fraction)
    except (TypeError, ValueError):
        raise ValueError("background fraction must be a float")
    if ratio < 0:
        raise ValueError("background fraction must be non-negative")
    if ratio == 0.0 or base_count == 0:
        return 0
    return int(math.ceil(base_count * ratio))


def generate_background_particles(
    rng: Any,
    count: int,
    *,
    wafer_radius_mm: float,
) -> list[dict[str, float]]:
    if count <= 0:
        return []
    if wafer_radius_mm <= 0:
        raise ValueError("wafer_radius_mm must be positive")
    particles: list[dict[str, float]] = []
    for _ in range(count):
        r_norm = math.sqrt(rng.random())
        theta_rad = rng.random() * math.tau
        particles.append({"r_norm": float(r_norm), "theta_rad": float(theta_rad)})
    return particles


def _normalize_theta(theta_rad: float) -> float:
    return float(theta_rad) % math.tau


def _clamp(value: float, min_value: float, max_value: float) -> float:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _resolve_r_mm(particle: dict[str, Any], wafer_radius_mm: float) -> float:
    if "r_mm" in particle and particle["r_mm"] is not None:
        return float(particle["r_mm"])
    if "r_norm" in particle and particle["r_norm"] is not None:
        return float(particle["r_norm"]) * wafer_radius_mm
    raise ValueError("particle missing r_mm/r_norm for jitter")
