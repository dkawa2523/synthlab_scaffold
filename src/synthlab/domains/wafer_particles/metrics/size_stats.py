from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from synthlab.framework.registry import register_metric

DEFAULT_QUANTILES = (0.05, 0.5, 0.95)


def compute_size_stats(
    sizes: Sequence[float],
    quantiles: Sequence[float] | None = None,
) -> dict[str, Any]:
    if quantiles is None:
        quantiles = DEFAULT_QUANTILES
    values = [float(value) for value in sizes]
    count = len(values)
    if count == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "quantiles": {},
        }

    mean = sum(values) / count
    variance = sum((value - mean) ** 2 for value in values) / count
    std = math.sqrt(variance)
    sorted_values = sorted(values)
    quantile_map = {
        _format_quantile_key(float(q)): _percentile(sorted_values, float(q))
        for q in quantiles
    }
    return {
        "count": count,
        "mean": mean,
        "std": std,
        "min": sorted_values[0],
        "max": sorted_values[-1],
        "quantiles": quantile_map,
    }


def compute_size_stats_from_particles(
    particles: Sequence[dict[str, Any]],
    *,
    size_key: str = "size_um",
    quantiles: Sequence[float] | None = None,
) -> dict[str, Any]:
    sizes = [_read_size(particle, size_key) for particle in particles]
    return compute_size_stats(sizes, quantiles=quantiles)


def compute_size_stats_by_label(
    particles: Sequence[dict[str, Any]],
    *,
    size_key: str = "size_um",
    label_key: str = "label",
    quantiles: Sequence[float] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, list[float]] = {}
    for particle in particles:
        label = _read_label(particle, label_key)
        grouped.setdefault(label, []).append(_read_size(particle, size_key))
    return {
        label: compute_size_stats(sizes, quantiles=quantiles)
        for label, sizes in grouped.items()
    }


@register_metric("wafer_particles.metric.size_stats_by_label")
def size_stats_by_label_metric(
    cfg: dict[str, Any] | None,
    tables: Mapping[str, Any],
) -> dict[str, Any]:
    cfg = cfg or {}
    if not isinstance(tables, Mapping):
        raise ValueError("tables must be a mapping")
    particles = tables.get("particles")
    if particles is None:
        raise ValueError("tables.particles is required")
    quantiles = cfg.get("quantiles")
    if quantiles is not None:
        quantiles = [float(value) for value in quantiles]
    size_key = str(cfg.get("size_key", "size_um"))
    label_key = str(cfg.get("label_key", "label"))
    return compute_size_stats_by_label(
        particles,
        size_key=size_key,
        label_key=label_key,
        quantiles=quantiles,
    )


def _read_size(particle: dict[str, Any], key: str) -> float:
    if key not in particle:
        raise ValueError(f"particle missing {key}")
    return float(particle[key])


def _read_label(particle: dict[str, Any], key: str) -> str:
    if key in particle:
        return str(particle[key])
    if key == "label" and "label_fine" in particle:
        return str(particle["label_fine"])
    raise ValueError(f"particle missing {key}")


def _format_quantile_key(q: float) -> str:
    if 0.0 <= q <= 1.0:
        return f"p{int(round(q * 100)):02d}"
    return str(q)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return math.nan
    if q <= 0:
        return float(sorted_values[0])
    if q >= 1:
        return float(sorted_values[-1])
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return float(sorted_values[lower])
    fraction = pos - lower
    lower_value = float(sorted_values[lower])
    upper_value = float(sorted_values[upper])
    return lower_value * (1.0 - fraction) + upper_value * fraction
