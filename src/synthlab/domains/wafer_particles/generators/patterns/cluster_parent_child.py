from __future__ import annotations

from math import sqrt
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import (
    build_particle,
    cartesian_to_polar_mm,
    resolve_sample_ctx,
    sample_poisson,
    sample_uniform_disk_xy,
)


@register_pattern("wafer_particles.pattern.cluster_parent_child")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    mean_particles = _resolve_mean_particles(cfg, ctx)
    mean_children = float(cfg.get("mean_children", 6.0))
    if mean_children <= 0:
        raise ValueError("mean_children must be positive")

    mean_parents = cfg.get("mean_parents")
    if mean_parents is None:
        mean_parents = mean_particles / mean_children if mean_particles > 0 else 0.0
    mean_parents = float(mean_parents)
    if mean_parents < 0:
        raise ValueError("mean_parents must be non-negative")

    n_parents = cfg.get("n_parents")
    if n_parents is None:
        n_parents = sample_poisson(rng, mean_parents)
    n_parents = int(n_parents)
    if n_parents < 0:
        raise ValueError("n_parents must be non-negative")

    children_per_parent = cfg.get("children_per_parent")
    if children_per_parent is not None:
        children_per_parent = int(children_per_parent)
        if children_per_parent < 0:
            raise ValueError("children_per_parent must be non-negative")

    sigma_mm = _resolve_sigma_mm(cfg, ctx.wafer_radius_mm)
    particles: list[dict[str, float | str]] = []
    for _ in range(n_parents):
        parent_x, parent_y = sample_uniform_disk_xy(rng, ctx.wafer_radius_mm)
        if children_per_parent is None:
            n_children = sample_poisson(rng, mean_children)
        else:
            n_children = children_per_parent
        if n_children <= 0:
            continue
        for _ in range(n_children):
            x_mm, y_mm = _sample_child(rng, parent_x, parent_y, sigma_mm, ctx.wafer_radius_mm)
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


def _resolve_sigma_mm(cfg: Mapping[str, Any], wafer_radius_mm: float) -> float:
    if "cluster_sigma_mm" in cfg:
        sigma_mm = float(cfg["cluster_sigma_mm"])
    else:
        ratio = float(cfg.get("cluster_sigma_ratio", 0.03))
        sigma_mm = ratio * wafer_radius_mm
    if sigma_mm <= 0:
        raise ValueError("cluster_sigma_mm must be positive")
    return sigma_mm


def _sample_child(
    rng: Any,
    parent_x_mm: float,
    parent_y_mm: float,
    sigma_mm: float,
    wafer_radius_mm: float,
) -> tuple[float, float]:
    radius_sq = wafer_radius_mm * wafer_radius_mm
    max_attempts = 30
    for _ in range(max_attempts):
        x_mm = parent_x_mm + rng.gauss(0.0, sigma_mm)
        y_mm = parent_y_mm + rng.gauss(0.0, sigma_mm)
        if x_mm * x_mm + y_mm * y_mm <= radius_sq:
            return x_mm, y_mm
    x_mm = parent_x_mm
    y_mm = parent_y_mm
    dist = sqrt(x_mm * x_mm + y_mm * y_mm)
    if dist <= 0.0:
        return sample_uniform_disk_xy(rng, wafer_radius_mm)
    scale = wafer_radius_mm / dist
    return x_mm * scale, y_mm * scale
