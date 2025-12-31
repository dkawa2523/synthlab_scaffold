from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle
from .geometry import sample_uniform_disk


@register_pattern("wafer_particles.pattern.random_uniform")
class RandomUniform(PatternBase):
    pattern_id = "wafer_particles.pattern.random_uniform"
    tags = ("random",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        points = sample_uniform_disk(rng, ctx.n_particles)
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]
