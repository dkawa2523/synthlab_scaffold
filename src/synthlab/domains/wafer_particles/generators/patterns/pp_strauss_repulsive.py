from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, cartesian_to_polar_norm, mm_to_norm, sample_poisson, sample_uniform_disk_xy


@register_pattern("wafer_particles.pattern.pp_strauss_repulsive")
class PpStraussRepulsive(PatternBase):
    pattern_id = "wafer_particles.pattern.pp_strauss_repulsive"
    tags = ("repulsive",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        target_count = _resolve_target_count(params, ctx, rng)
        if target_count <= 0:
            return []

        min_distance_norm = _resolve_min_distance_norm(params, ctx)
        max_attempts = int(params.get("max_attempts", max(200, target_count * 80)))
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")

        points: list[tuple[float, float]] = []
        grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        origin = -1.0
        min_dist_sq = min_distance_norm * min_distance_norm
        attempts = 0

        while len(points) < target_count and attempts < max_attempts:
            attempts += 1
            x_norm, y_norm = sample_uniform_disk_xy(rng)
            if _accept_point(x_norm, y_norm, grid, origin, min_distance_norm, min_dist_sq):
                points.append((x_norm, y_norm))
                _store_point(x_norm, y_norm, grid, origin, min_distance_norm)

        particles: list[dict[str, Any]] = []
        for x_norm, y_norm in points:
            r_norm, theta_rad = cartesian_to_polar_norm(x_norm, y_norm)
            particles.append(build_particle(r_norm, theta_rad))
        return particles


def _resolve_target_count(cfg: Mapping[str, Any], ctx: PatternContext, rng: Any) -> int:
    if "n_particles" in cfg and cfg.get("n_particles") is not None:
        count = int(cfg["n_particles"])
        if count < 0:
            raise ValueError("n_particles must be non-negative")
        return count
    mean_particles = cfg.get("mean_particles")
    if mean_particles is None:
        return int(ctx.n_particles)
    mean_particles = float(mean_particles)
    if mean_particles < 0:
        raise ValueError("mean_particles must be non-negative")
    return sample_poisson(rng, mean_particles)


def _resolve_min_distance_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "min_distance_norm" in cfg and cfg.get("min_distance_norm") is not None:
        min_distance_norm = float(cfg["min_distance_norm"])
    elif "min_distance_mm" in cfg and cfg.get("min_distance_mm") is not None:
        min_distance_norm = mm_to_norm(float(cfg["min_distance_mm"]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get("min_distance_ratio", 0.03))
        min_distance_norm = ratio
    if min_distance_norm <= 0:
        raise ValueError("min_distance must be positive")
    return min_distance_norm


def _accept_point(
    x_norm: float,
    y_norm: float,
    grid: Mapping[tuple[int, int], list[tuple[float, float]]],
    origin: float,
    cell_size: float,
    min_dist_sq: float,
) -> bool:
    ix, iy = _grid_index(x_norm, y_norm, origin, cell_size)
    for nx in range(ix - 1, ix + 2):
        for ny in range(iy - 1, iy + 2):
            for px_norm, py_norm in grid.get((nx, ny), []):
                dx = x_norm - px_norm
                dy = y_norm - py_norm
                if dx * dx + dy * dy < min_dist_sq:
                    return False
    return True


def _store_point(
    x_norm: float,
    y_norm: float,
    grid: dict[tuple[int, int], list[tuple[float, float]]],
    origin: float,
    cell_size: float,
) -> None:
    key = _grid_index(x_norm, y_norm, origin, cell_size)
    grid.setdefault(key, []).append((x_norm, y_norm))


def _grid_index(x_norm: float, y_norm: float, origin: float, cell_size: float) -> tuple[int, int]:
    ix = int((x_norm - origin) / cell_size)
    iy = int((y_norm - origin) / cell_size)
    return ix, iy
