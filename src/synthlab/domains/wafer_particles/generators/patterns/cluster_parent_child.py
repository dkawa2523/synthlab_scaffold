from __future__ import annotations

from math import sqrt
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, cartesian_to_polar_norm, mm_to_norm, sample_poisson, sample_uniform_disk_xy


@register_pattern("wafer_particles.pattern.cluster_parent_child")
class ClusterParentChild(PatternBase):
    pattern_id = "wafer_particles.pattern.cluster_parent_child"
    tags = ("cluster",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        mean_particles = _resolve_mean_particles(params, ctx)
        mean_children = float(params.get("mean_children", 6.0))
        if mean_children <= 0:
            raise ValueError("mean_children must be positive")

        mean_parents = params.get("mean_parents")
        if mean_parents is None:
            mean_parents = mean_particles / mean_children if mean_particles > 0 else 0.0
        mean_parents = float(mean_parents)
        if mean_parents < 0:
            raise ValueError("mean_parents must be non-negative")

        n_parents = params.get("n_parents")
        if n_parents is None:
            n_parents = sample_poisson(rng, mean_parents)
        n_parents = int(n_parents)
        if n_parents < 0:
            raise ValueError("n_parents must be non-negative")

        children_per_parent = params.get("children_per_parent")
        if children_per_parent is not None:
            children_per_parent = int(children_per_parent)
            if children_per_parent < 0:
                raise ValueError("children_per_parent must be non-negative")

        sigma_norm = _resolve_sigma_norm(params, ctx)
        particles: list[dict[str, Any]] = []
        for _ in range(n_parents):
            parent_x, parent_y = sample_uniform_disk_xy(rng)
            if children_per_parent is None:
                n_children = sample_poisson(rng, mean_children)
            else:
                n_children = children_per_parent
            if n_children <= 0:
                continue
            for _ in range(n_children):
                x_norm, y_norm = _sample_child(rng, parent_x, parent_y, sigma_norm)
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


def _resolve_sigma_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "cluster_sigma_norm" in cfg:
        sigma_norm = float(cfg["cluster_sigma_norm"])
    elif "cluster_sigma_mm" in cfg:
        sigma_norm = mm_to_norm(float(cfg["cluster_sigma_mm"]), ctx.wafer_radius_mm)
    else:
        ratio = float(cfg.get("cluster_sigma_ratio", 0.03))
        sigma_norm = ratio
    if sigma_norm <= 0:
        raise ValueError("cluster_sigma must be positive")
    return sigma_norm


def _sample_child(
    rng: Any,
    parent_x_norm: float,
    parent_y_norm: float,
    sigma_norm: float,
) -> tuple[float, float]:
    max_attempts = 30
    for _ in range(max_attempts):
        x_norm = parent_x_norm + rng.gauss(0.0, sigma_norm)
        y_norm = parent_y_norm + rng.gauss(0.0, sigma_norm)
        if x_norm * x_norm + y_norm * y_norm <= 1.0:
            return x_norm, y_norm
    x_norm = parent_x_norm
    y_norm = parent_y_norm
    dist = sqrt(x_norm * x_norm + y_norm * y_norm)
    if dist <= 0.0:
        return sample_uniform_disk_xy(rng)
    scale = 1.0 / dist
    return x_norm * scale, y_norm * scale
