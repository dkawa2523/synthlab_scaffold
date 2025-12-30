from __future__ import annotations

from math import tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import build_particle, resolve_sample_ctx


@register_pattern("wafer_particles.pattern.random_edge_biased")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    edge_bias = float(cfg.get("edge_bias", 2.0))
    if edge_bias <= 0:
        raise ValueError("edge_bias must be positive")

    exponent = 0.5 / edge_bias
    particles: list[dict[str, float | str]] = []
    for _ in range(ctx.n_particles):
        r_mm = ctx.wafer_radius_mm * (rng.random() ** exponent)
        theta_rad = rng.random() * tau
        particles.append(build_particle(r_mm, theta_rad))
    return particles
