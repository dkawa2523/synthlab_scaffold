from __future__ import annotations

from math import exp, sqrt
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import (
    build_particle,
    cartesian_to_polar_mm,
    resolve_sample_ctx,
    sample_poisson,
    sample_uniform_disk_xy,
)


@register_pattern("wafer_particles.pattern.cox_lognormal")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    mean_particles = _resolve_mean_particles(cfg, ctx)
    if mean_particles <= 0:
        return []

    grid_bins = int(cfg.get("grid_bins", 8))
    if grid_bins <= 0:
        raise ValueError("grid_bins must be positive")
    field_sigma = float(cfg.get("field_sigma", 0.8))
    if field_sigma < 0:
        raise ValueError("field_sigma must be non-negative")

    cells = _build_cells(rng, ctx.wafer_radius_mm, grid_bins, field_sigma)
    weights = [cell[4] for cell in cells]
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("cox field weights must sum to > 0")
    cumulative = _cumulative_weights(weights)

    n_points = sample_poisson(rng, float(mean_particles))
    if n_points <= 0:
        return []

    particles: list[dict[str, float | str]] = []
    max_attempts = int(cfg.get("max_attempts", max(100, n_points * 40)))
    attempts = 0
    while len(particles) < n_points and attempts < max_attempts:
        attempts += 1
        idx = _sample_index(rng, cumulative, total_weight)
        x0, x1, y0, y1, _ = cells[idx]
        x_mm = rng.uniform(x0, x1)
        y_mm = rng.uniform(y0, y1)
        if x_mm * x_mm + y_mm * y_mm <= ctx.wafer_radius_mm * ctx.wafer_radius_mm:
            r_mm, theta_rad = cartesian_to_polar_mm(x_mm, y_mm)
            particles.append(build_particle(r_mm, theta_rad))

    while len(particles) < n_points:
        x_mm, y_mm = sample_uniform_disk_xy(rng, ctx.wafer_radius_mm)
        r_mm, theta_rad = cartesian_to_polar_mm(x_mm, y_mm)
        particles.append(build_particle(r_mm, theta_rad))

    return particles


def _resolve_mean_particles(cfg: Mapping[str, Any], ctx: Any) -> float:
    mean_particles = cfg.get("mean_particles")
    if mean_particles is None:
        mean_particles = cfg.get("n_particles")
    if mean_particles is None:
        mean_particles = ctx.n_particles
    mean_particles = float(mean_particles)
    if mean_particles < 0:
        raise ValueError("mean_particles must be non-negative")
    return mean_particles


def _build_cells(
    rng: Any,
    wafer_radius_mm: float,
    grid_bins: int,
    field_sigma: float,
) -> list[tuple[float, float, float, float, float]]:
    cell_size = (2.0 * wafer_radius_mm) / grid_bins
    radius_sq = wafer_radius_mm * wafer_radius_mm
    cells: list[tuple[float, float, float, float, float]] = []
    for ix in range(grid_bins):
        x0 = -wafer_radius_mm + ix * cell_size
        x1 = x0 + cell_size
        cx = (x0 + x1) / 2.0
        for iy in range(grid_bins):
            y0 = -wafer_radius_mm + iy * cell_size
            y1 = y0 + cell_size
            cy = (y0 + y1) / 2.0
            if cx * cx + cy * cy > radius_sq:
                continue
            weight = exp(field_sigma * rng.gauss(0.0, 1.0))
            cells.append((x0, x1, y0, y1, weight))
    if not cells:
        raise ValueError("cox grid has no cells inside wafer")
    return cells


def _cumulative_weights(weights: list[float]) -> list[float]:
    cumulative: list[float] = []
    running = 0.0
    for weight in weights:
        running += weight
        cumulative.append(running)
    return cumulative


def _sample_index(rng: Any, cumulative: list[float], total: float) -> int:
    target = rng.random() * total
    lo = 0
    hi = len(cumulative) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if target <= cumulative[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo
