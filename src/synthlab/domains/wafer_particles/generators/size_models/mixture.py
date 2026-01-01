from __future__ import annotations

from bisect import bisect_left
import math
from typing import Any, Mapping

from synthlab.framework.registry import get_size_model, register_size_model
from synthlab.domains.wafer_particles.generators.size_models.common import normalize_size_model_name


@register_size_model("wafer_particles.size_model.mixture")
def assign(
    cfg: Mapping[str, Any],
    rng: Any,
    particles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not particles:
        return particles
    components = cfg.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("mixture requires components list")

    weights: list[float] = []
    component_cfgs: list[dict[str, Any]] = []
    for idx, component in enumerate(components):
        if not isinstance(component, Mapping):
            raise ValueError(f"component {idx} must be a mapping")
        weight = float(component.get("weight", 1.0))
        if weight <= 0:
            raise ValueError("mixture component weight must be positive")
        component_cfg = _resolve_component_cfg(component, idx)
        weights.append(weight)
        component_cfgs.append(component_cfg)

    total = sum(weights)
    if total <= 0:
        raise ValueError("mixture component weights must be positive")
    if not math.isclose(total, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("mixture component weights must sum to 1")
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
    min_um, max_um = _resolve_bounds(cfg)
    if min_um is not None or max_um is not None:
        _apply_final_bounds(particles, min_um, max_um)
    return particles


def _resolve_component_cfg(component: Mapping[str, Any], idx: int) -> dict[str, Any]:
    model_entry = component.get("model")
    if isinstance(model_entry, Mapping):
        model_cfg: dict[str, Any] = dict(model_entry)
    else:
        cfg_entry = component.get("cfg") or {}
        if not isinstance(cfg_entry, Mapping):
            raise ValueError(f"component {idx} cfg must be a mapping")
        model_cfg = dict(cfg_entry)
        if model_entry is not None:
            if not isinstance(model_entry, str):
                raise ValueError(f"component {idx} model must be a mapping or string")
            if not model_cfg.get("type") and not model_cfg.get("name"):
                model_cfg["type"] = model_entry

    model_name = model_cfg.get("type") or model_cfg.get("name")
    if not model_name:
        component_type = component.get("type")
        if component_type:
            model_name = component_type
    if not model_name:
        raise ValueError(f"component {idx} requires model")
    model_cfg.setdefault("type", model_name)
    model_cfg["name"] = normalize_size_model_name(model_cfg.get("type") or model_cfg.get("name"))
    model_cfg.pop("by_label", None)
    return model_cfg


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


def _resolve_bounds(cfg: Mapping[str, Any]) -> tuple[float | None, float | None]:
    min_um = cfg.get("min_um")
    max_um = cfg.get("max_um")
    min_value = float(min_um) if min_um is not None else None
    max_value = float(max_um) if max_um is not None else None
    if min_value is not None and max_value is not None and max_value < min_value:
        raise ValueError("max_um must be >= min_um")
    return min_value, max_value


def _apply_final_bounds(particles: list[dict[str, Any]], min_um: float | None, max_um: float | None) -> None:
    for particle in particles:
        size_um = particle.get("size_um")
        if size_um is None:
            continue
        value = float(size_um)
        if min_um is not None and value < min_um:
            value = min_um
        if max_um is not None and value > max_um:
            value = max_um
        particle["size_um"] = float(value)
