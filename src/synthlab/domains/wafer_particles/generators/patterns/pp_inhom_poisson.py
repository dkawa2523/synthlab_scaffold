from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .inhomogeneous_poisson import InhomogeneousPoisson


@register_pattern("wafer_particles.pattern.pp_inhom_poisson")
class PpInhomPoisson(PatternBase):
    pattern_id = "wafer_particles.pattern.pp_inhom_poisson"
    tags = ("poisson",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        return InhomogeneousPoisson.generate(ctx, params, rng)
