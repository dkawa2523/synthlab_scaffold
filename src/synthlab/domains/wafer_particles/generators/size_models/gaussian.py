from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_size_model


@register_size_model("wafer_particles.size_model.gaussian")
def assign(
    cfg: Mapping[str, Any],
    rng: Any,
    particles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mean_um = float(cfg.get("mean_um", 1.0))
    std_um = float(cfg.get("std_um", 0.2))
    if std_um < 0:
        raise ValueError("std_um must be non-negative")
    min_um, max_um = _resolve_bounds(cfg)

    for particle in particles:
        size_um = rng.gauss(mean_um, std_um)
        size_um = _apply_bounds(size_um, min_um, max_um)
        particle["size_um"] = float(size_um)
    return particles


def _resolve_bounds(cfg: Mapping[str, Any]) -> tuple[float | None, float | None]:
    min_um = cfg.get("min_um")
    max_um = cfg.get("max_um")
    min_value = float(min_um) if min_um is not None else None
    max_value = float(max_um) if max_um is not None else None
    if min_value is not None and max_value is not None and max_value < min_value:
        raise ValueError("max_um must be >= min_um")
    return min_value, max_value


def _apply_bounds(value: float, min_um: float | None, max_um: float | None) -> float:
    if min_um is not None and value < min_um:
        return min_um
    if max_um is not None and value > max_um:
        return max_um
    return value
