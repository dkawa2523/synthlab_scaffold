from __future__ import annotations

from bisect import bisect_left
from typing import Any, Mapping

from synthlab.framework.registry import get_size_model, register_size_model


@register_size_model("wafer_particles.size_model.mixture")
def assign(
    cfg: Mapping[str, Any],
    rng: Any,
    particles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    components = cfg.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("mixture requires components list")

    weights: list[float] = []
    component_cfgs: list[dict[str, Any]] = []
    for idx, component in enumerate(components):
        if not isinstance(component, Mapping):
            raise ValueError(f"component {idx} must be a mapping")
        weight = float(component.get("weight", 1.0))
        if weight < 0:
            raise ValueError("mixture component weight must be non-negative")
        component_cfg = component.get("cfg")
        if component_cfg is None:
            component_cfg = {}
        if not isinstance(component_cfg, Mapping):
            raise ValueError("component.cfg must be a mapping")
        component_cfg = dict(component_cfg)
        if "name" not in component_cfg:
            model_name = component.get("model") or component.get("name")
            if not model_name:
                raise ValueError("component.model is required")
            component_cfg["name"] = str(model_name)
        component_cfg.pop("by_label", None)
        weights.append(weight)
        component_cfgs.append(component_cfg)

    total = sum(weights)
    if total <= 0:
        raise ValueError("mixture component weights must be positive")
    cumulative = _build_cumulative(weights, total)

    grouped: list[list[dict[str, Any]]] = [[] for _ in component_cfgs]
    for particle in particles:
        idx = _select_component(cumulative, rng.random())
        grouped[idx].append(particle)

    for component_cfg, group in zip(component_cfgs, grouped):
        if not group:
            continue
        model = get_size_model(str(component_cfg["name"]))
        model(component_cfg, rng, group)
    return particles


def _build_cumulative(weights: list[float], total: float) -> list[float]:
    cumulative: list[float] = []
    acc = 0.0
    for weight in weights:
        acc += weight / total
        cumulative.append(acc)
    return cumulative


def _select_component(cumulative: list[float], value: float) -> int:
    idx = bisect_left(cumulative, value)
    if idx >= len(cumulative):
        return len(cumulative) - 1
    return idx
