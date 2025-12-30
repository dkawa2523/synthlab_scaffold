from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.domains.wafer_particles.metrics.size_stats  # noqa: E402,F401
from synthlab.framework.registry import get_metric, list_metrics, register_metric  # noqa: E402


def test_metric_registry_contains_expected_key() -> None:
    keys = set(list_metrics())
    assert "wafer_particles.metric.size_stats_by_label" in keys


def test_metric_registry_smoke_call() -> None:
    metric = get_metric("wafer_particles.metric.size_stats_by_label")
    particles = [
        {"label": "a", "size_um": 1.0},
        {"label": "a", "size_um": 2.0},
        {"label": "b", "size_um": 3.0},
    ]
    result = metric({"quantiles": [0.5]}, {"particles": particles})
    assert result["a"]["count"] == 2
    assert result["a"]["quantiles"]["p50"] == 1.5


def test_registry_enforces_namespaced_keys_and_duplicates() -> None:
    def echo_metric(cfg: dict[str, object] | None, tables: dict[str, object]) -> dict[str, bool]:
        return {"ok": True}

    with pytest.raises(ValueError):
        register_metric("metric")(echo_metric)

    key = "test.metric.echo_registry"
    register_metric(key)(echo_metric)
    assert get_metric(key)({}, {})["ok"] is True

    with pytest.warns(RuntimeWarning, match="metric already registered"):
        with pytest.raises(ValueError):
            register_metric(key)(echo_metric)
