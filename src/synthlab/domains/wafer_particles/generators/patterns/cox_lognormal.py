from __future__ import annotations

from math import exp
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, cartesian_to_polar_norm, sample_poisson, sample_uniform_disk_xy


@register_pattern("wafer_particles.pattern.cox_lognormal")
class CoxLognormal(PatternBase):
    pattern_id = "wafer_particles.pattern.cox_lognormal"
    tags = ("cox",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        mean_particles = _resolve_mean_particles(params, ctx)
        if mean_particles <= 0:
            return []

        grid_bins = int(params.get("grid_bins", 8))
        if grid_bins <= 0:
            raise ValueError("grid_bins must be positive")
        field_sigma = float(params.get("field_sigma", 0.8))
        if field_sigma < 0:
            raise ValueError("field_sigma must be non-negative")

        cells = _build_cells(rng, grid_bins, field_sigma)
        weights = [cell[4] for cell in cells]
        total_weight = sum(weights)
        if total_weight <= 0:
            raise ValueError("cox field weights must sum to > 0")
        cumulative = _cumulative_weights(weights)

        n_points = sample_poisson(rng, float(mean_particles))
        if n_points <= 0:
            return []

        particles: list[dict[str, Any]] = []
        max_attempts = int(params.get("max_attempts", max(100, n_points * 40)))
        attempts = 0
        while len(particles) < n_points and attempts < max_attempts:
            attempts += 1
            idx = _sample_index(rng, cumulative, total_weight)
            x0, x1, y0, y1, _ = cells[idx]
            x_norm = rng.uniform(x0, x1)
            y_norm = rng.uniform(y0, y1)
            if x_norm * x_norm + y_norm * y_norm <= 1.0:
                r_norm, theta_rad = cartesian_to_polar_norm(x_norm, y_norm)
                particles.append(build_particle(r_norm, theta_rad))

        while len(particles) < n_points:
            x_norm, y_norm = sample_uniform_disk_xy(rng)
            r_norm, theta_rad = cartesian_to_polar_norm(x_norm, y_norm)
            particles.append(build_particle(r_norm, theta_rad))

        return particles


def _resolve_mean_particles(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
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
    grid_bins: int,
    field_sigma: float,
) -> list[tuple[float, float, float, float, float]]:
    cell_size = 2.0 / grid_bins
    cells: list[tuple[float, float, float, float, float]] = []
    for ix in range(grid_bins):
        x0 = -1.0 + ix * cell_size
        x1 = x0 + cell_size
        cx = (x0 + x1) / 2.0
        for iy in range(grid_bins):
            y0 = -1.0 + iy * cell_size
            y1 = y0 + cell_size
            cy = (y0 + y1) / 2.0
            if cx * cx + cy * cy > 1.0:
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
