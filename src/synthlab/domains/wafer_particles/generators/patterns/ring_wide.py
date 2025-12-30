from __future__ import annotations

from math import tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import build_particle, resolve_radius_mm, resolve_sample_ctx, resolve_width_mm


@register_pattern("wafer_particles.pattern.ring_wide")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    radius_mm = resolve_radius_mm(cfg, ctx, default_ratio=0.6)
    width_mm = resolve_width_mm(cfg, ctx, default_ratio=0.15)

    particles: list[dict[str, float | str]] = []
    for _ in range(ctx.n_particles):
        r_mm = radius_mm + (rng.random() - 0.5) * width_mm
        r_mm = min(max(r_mm, 0.0), ctx.wafer_radius_mm)
        theta_rad = rng.random() * tau
        particles.append(build_particle(r_mm, theta_rad))
    return particles
