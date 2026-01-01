from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import get_size_model


def normalize_size_model_name(name: Any) -> str:
    if name is None or name == "":
        raise ValueError("size model name is required")
    name_str = str(name)
    if "." in name_str:
        return name_str
    return f"wafer_particles.size_model.{name_str}"


def resolve_size_model_name(cfg: Mapping[str, Any]) -> str:
    name = cfg.get("type")
    if name is None or name == "":
        name = cfg.get("name")
    return normalize_size_model_name(name)


def apply_size_model(
    cfg: Mapping[str, Any],
    rng: Any,
    particles: list[dict[str, Any]],
    *,
    label_key: str = "label",
) -> list[dict[str, Any]]:
    if not isinstance(cfg, Mapping):
        raise ValueError("size model config must be a mapping")
    if not particles:
        return particles

    by_label = cfg.get("by_label")
    if by_label is None:
        _apply_model(_strip_by_label(cfg), rng, particles)
        return particles
    if not isinstance(by_label, Mapping):
        raise ValueError("size model by_label must be a mapping")

    labels, grouped = _group_by_label(particles, label_key)
    for label in labels:
        label_cfg = by_label.get(label)
        merged_cfg = _merge_cfg(cfg, label_cfg)
        _apply_model(merged_cfg, rng, grouped[label])
    return particles


def _apply_model(cfg: Mapping[str, Any], rng: Any, particles: list[dict[str, Any]]) -> None:
    name = resolve_size_model_name(cfg)
    model = get_size_model(name)
    model(cfg, rng, particles)


def _strip_by_label(cfg: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = dict(cfg)
    cleaned.pop("by_label", None)
    return cleaned


def _merge_cfg(base_cfg: Mapping[str, Any], label_cfg: Any) -> dict[str, Any]:
    merged = _strip_by_label(base_cfg)
    if label_cfg is None:
        return merged
    if not isinstance(label_cfg, Mapping):
        raise ValueError("label size model config must be a mapping")
    for key, value in label_cfg.items():
        merged[key] = value
    merged.pop("by_label", None)
    return merged


def _group_by_label(
    particles: list[dict[str, Any]],
    label_key: str,
) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
    order: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for particle in particles:
        if label_key not in particle:
            raise ValueError(f"particle missing {label_key}")
        label = str(particle[label_key])
        if label not in grouped:
            grouped[label] = []
            order.append(label)
        grouped[label].append(particle)
    return order, grouped
