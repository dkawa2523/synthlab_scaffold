from __future__ import annotations

import warnings
from math import tau
from typing import Any, Mapping

from synthlab.domains.wafer_particles import param_space
from synthlab.framework.registry import get_pattern, register_pattern

from .base import PatternBase, PatternContext

_PATTERN_KEY = "wafer_particles.pattern.composite"


@register_pattern(_PATTERN_KEY)
class Composite(PatternBase):
    pattern_id = _PATTERN_KEY
    tags = ("composite",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        components = params.get("components")
        if not isinstance(components, list) or not components:
            raise ValueError("composite requires components")

        weights: list[float] = []
        component_entries: list[dict[str, Any]] = []
        for idx, component in enumerate(components):
            if not isinstance(component, Mapping):
                raise ValueError(f"component {idx} must be a mapping")
            weight = float(component.get("weight", 1.0))
            if weight < 0:
                raise ValueError("composite weights must be non-negative")
            weights.append(weight)
            component_entries.append(dict(component))
        total = sum(weights)
        if total <= 0:
            raise ValueError("composite weights must be positive")

        counts = _allocate_counts(ctx.n_particles, weights)
        particles: list[dict[str, Any]] = []
        for component_id, (component, count) in enumerate(zip(component_entries, counts)):
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
            component_label = _resolve_component_label(component, pattern_name)
            transform_cfg = component.get("transform")
            if transform_cfg is None:
                transform_cfg = {}
            if not isinstance(transform_cfg, Mapping):
                raise ValueError("component.transform must be a mapping if provided")
            transform = _resolve_transform(dict(transform_cfg), rng)
            component_ctx = PatternContext(
                n_particles=count,
                wafer_radius_mm=ctx.wafer_radius_mm,
            )
            component_particles = generator.generate(component_ctx, component_cfg, rng)
            if transform:
                _apply_transform(component_particles, transform, rng)
            for particle in component_particles:
                if "component_label_fine" not in particle:
                    particle["component_label_fine"] = str(component_label)
                if "component_id" not in particle:
                    particle["component_id"] = int(component_id)
            particles.extend(component_particles)

        return particles


def _resolve_component_label(component: Mapping[str, Any], fallback: str) -> str:
    if "component_label_fine" in component:
        return str(component["component_label_fine"])
    if "label" in component:
        warnings.warn("component.label is deprecated; use component_label_fine", RuntimeWarning, stacklevel=3)
        return str(component["label"])
    return str(fallback)


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


def _resolve_transform(cfg: Mapping[str, Any], rng: Any) -> dict[str, float | bool]:
    if not cfg:
        return {}
    param_rng = param_space.numpy_rng_from_random(rng)
    rotate_spec = cfg.get("rotate_theta_rad")
    if rotate_spec is None:
        rotate_spec = 0.0
    radial_spec = cfg.get("radial_scale")
    if radial_spec is None:
        radial_spec = 1.0
    rotate = float(
        param_space.sample_param_spec(
            rotate_spec,
            param_rng,
            "transform.rotate_theta_rad",
            base_value=0.0,
            allow_legacy_range=True,
        )
    )
    radial_scale = float(
        param_space.sample_param_spec(
            radial_spec,
            param_rng,
            "transform.radial_scale",
            base_value=1.0,
            allow_legacy_range=True,
        )
    )
    if radial_scale < 0:
        raise ValueError("transform.radial_scale must be non-negative")
    mirror = bool(cfg.get("mirror_theta", False))
    theta_jitter = _resolve_float(cfg.get("theta_jitter_std"), "theta_jitter_std", default=0.0)
    r_jitter = _resolve_float(cfg.get("r_jitter_std"), "r_jitter_std", default=0.0)
    if theta_jitter < 0 or r_jitter < 0:
        raise ValueError("transform jitter std must be non-negative")
    return {
        "rotate_theta_rad": rotate,
        "radial_scale": radial_scale,
        "mirror_theta": mirror,
        "theta_jitter_std": theta_jitter,
        "r_jitter_std": r_jitter,
    }


def _resolve_float(value: Any, name: str, *, default: float) -> float:
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc


def _apply_transform(
    particles: list[dict[str, Any]],
    transform: Mapping[str, float | bool],
    rng: Any,
) -> None:
    rotate = float(transform.get("rotate_theta_rad", 0.0))
    radial_scale = float(transform.get("radial_scale", 1.0))
    mirror = bool(transform.get("mirror_theta", False))
    theta_jitter = float(transform.get("theta_jitter_std", 0.0))
    r_jitter = float(transform.get("r_jitter_std", 0.0))
    for particle in particles:
        r_norm = float(particle["r_norm"]) * radial_scale
        theta_rad = float(particle["theta_rad"]) + rotate
        if mirror:
            theta_rad = -theta_rad
        if r_jitter > 0.0:
            r_norm += rng.gauss(0.0, r_jitter)
        if theta_jitter > 0.0:
            theta_rad += rng.gauss(0.0, theta_jitter)
        if r_norm < 0.0:
            r_norm = 0.0
        if r_norm > 1.0:
            r_norm = 1.0
        particle["r_norm"] = r_norm
        particle["theta_rad"] = float(theta_rad) % tau
