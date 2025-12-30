from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import get_pattern, register_pattern

from .common import resolve_sample_ctx

_PATTERN_KEY = "wafer_particles.pattern.composite"


@register_pattern(_PATTERN_KEY)
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    components = cfg.get("components")
    if not components:
        raise ValueError("composite requires components")

    weights = [float(component.get("weight", 1.0)) for component in components]
    total = sum(weights)
    if total <= 0:
        raise ValueError("composite weights must be positive")

    counts = _allocate_counts(ctx.n_particles, weights)
    particles: list[dict[str, float | str]] = []
    for component, count in zip(components, counts):
        if count <= 0:
            continue
        pattern_name = str(component.get("pattern", ""))
        if not pattern_name:
            raise ValueError("component.pattern is required")
        if pattern_name == _PATTERN_KEY:
            raise ValueError("composite cannot reference itself")
        generator = get_pattern(pattern_name)
        component_cfg = component.get("cfg")
        if component_cfg is None:
            component_cfg = {}
        if not isinstance(component_cfg, Mapping):
            raise ValueError("component.cfg must be a mapping if provided")
        component_cfg = dict(component_cfg)
        component_label = component.get("label", pattern_name)
        component_ctx = {
            "n_particles": count,
            "wafer_radius_mm": ctx.wafer_radius_mm,
        }
        component_particles = generator(component_cfg, rng, component_ctx)
        for particle in component_particles:
            if "component" not in particle:
                particle["component"] = str(component_label)
        particles.extend(component_particles)

    return particles


def _allocate_counts(total_particles: int, weights: list[float]) -> list[int]:
    raw = [total_particles * weight / sum(weights) for weight in weights]
    counts = [int(value) for value in raw]
    remainder = total_particles - sum(counts)
    if remainder <= 0:
        return counts
    fractions = [value - int(value) for value in raw]
    order = sorted(range(len(fractions)), key=lambda idx: (-fractions[idx], idx))
    for idx in range(remainder):
        counts[order[idx]] += 1
    return counts
