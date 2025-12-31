from __future__ import annotations

from math import tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, resolve_radius_norm, resolve_width_norm
from .geometry import sample_uniform_annulus


@register_pattern("wafer_particles.pattern.ring_wide")
class RingWide(PatternBase):
    pattern_id = "wafer_particles.pattern.ring_wide"
    tags = ("ring",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        radius_norm = resolve_radius_norm(params, ctx, default_ratio=0.6)
        width_norm = resolve_width_norm(params, ctx, default_ratio=0.15)
        r_inner = max(0.0, radius_norm - width_norm * 0.5)
        r_outer = min(1.0, radius_norm + width_norm * 0.5)
        points = sample_uniform_annulus(rng, ctx.n_particles, r_inner=r_inner, r_outer=r_outer)
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]
