from __future__ import annotations

from math import tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle
from .geometry import sample_uniform_disk


@register_pattern("wafer_particles.pattern.C01_Uniform")
class C01Uniform(PatternBase):
    pattern_id = "C01_Uniform"
    tags = ("uniform",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        points = sample_uniform_disk(rng, ctx.n_particles)
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


@register_pattern("wafer_particles.pattern.C02_EdgeBiased")
class C02EdgeBiased(PatternBase):
    pattern_id = "C02_EdgeBiased"
    touch_edge = True
    tags = ("edge", "random")

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
