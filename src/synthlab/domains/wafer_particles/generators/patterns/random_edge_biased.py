from __future__ import annotations

from math import tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle


@register_pattern("wafer_particles.pattern.random_edge_biased")
class RandomEdgeBiased(PatternBase):
    pattern_id = "wafer_particles.pattern.random_edge_biased"
    touch_edge = True
    tags = ("random", "edge")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        edge_bias = float(params.get("edge_bias", 2.0))
        if edge_bias <= 0:
            raise ValueError("edge_bias must be positive")

        exponent = 0.5 / edge_bias
        particles: list[dict[str, Any]] = []
        for _ in range(ctx.n_particles):
            r_norm = rng.random() ** exponent
            theta_rad = rng.random() * tau
            particles.append(build_particle(r_norm, theta_rad))
        return particles
