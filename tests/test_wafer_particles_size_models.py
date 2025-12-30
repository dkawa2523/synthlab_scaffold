from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synthlab.domains.wafer_particles.generators.size_models  # noqa: E402,F401
from synthlab.domains.wafer_particles.generators.size_models.common import (  # noqa: E402
    apply_size_model,
)
from synthlab.domains.wafer_particles.metrics.size_stats import (  # noqa: E402
    compute_size_stats_by_label,
)
from synthlab.framework.registry import get_size_model, list_size_models  # noqa: E402


SIZE_MODEL_KEYS = [
    "wafer_particles.size_model.gaussian",
    "wafer_particles.size_model.lognormal",
    "wafer_particles.size_model.mixture",
]


def _apply_model(cfg: dict[str, object], seed: int = 123) -> list[float]:
    rng = random.Random(seed)
    particles = [{"label": "default"} for _ in range(8)]
    model = get_size_model(str(cfg["name"]))
    model(cfg, rng, particles)
    return [float(particle["size_um"]) for particle in particles]


def test_size_model_registry_contains_expected_keys() -> None:
    keys = set(list_size_models())
    for key in SIZE_MODEL_KEYS:
        assert key in keys


@pytest.mark.parametrize(
    "cfg",
    [
        {"name": "wafer_particles.size_model.gaussian", "mean_um": 1.0, "std_um": 0.3},
        {"name": "wafer_particles.size_model.lognormal", "mu_log": -0.2, "sigma_log": 0.4},
        {
            "name": "wafer_particles.size_model.mixture",
            "components": [
                {
                    "model": "wafer_particles.size_model.gaussian",
                    "weight": 0.6,
                    "cfg": {"mean_um": 1.0, "std_um": 0.2},
                },
                {
                    "model": "wafer_particles.size_model.lognormal",
                    "weight": 0.4,
                    "cfg": {"mu_log": 0.1, "sigma_log": 0.3},
                },
            ],
        },
    ],
)
def test_size_models_are_deterministic(cfg: dict[str, object]) -> None:
    out_a = _apply_model(cfg, seed=7)
    out_b = _apply_model(cfg, seed=7)
    assert out_a == out_b


def test_apply_size_model_by_label() -> None:
    cfg = {
        "name": "wafer_particles.size_model.gaussian",
        "mean_um": 1.0,
        "std_um": 0.0,
        "by_label": {
            "big": {"mean_um": 10.0, "std_um": 0.0},
        },
    }
    rng = random.Random(5)
    particles = [
        {"label": "small"},
        {"label": "big"},
        {"label": "small"},
    ]
    apply_size_model(cfg, rng, particles)

    sizes_small = [p["size_um"] for p in particles if p["label"] == "small"]
    sizes_big = [p["size_um"] for p in particles if p["label"] == "big"]
    assert sizes_small == [1.0, 1.0]
    assert sizes_big == [10.0]


def test_mixture_assigns_component_values() -> None:
    cfg = {
        "name": "wafer_particles.size_model.mixture",
        "components": [
            {
                "model": "wafer_particles.size_model.gaussian",
                "weight": 0.5,
                "cfg": {"mean_um": 1.0, "std_um": 0.0},
            },
            {
                "model": "wafer_particles.size_model.gaussian",
                "weight": 0.5,
                "cfg": {"mean_um": 10.0, "std_um": 0.0},
            },
        ],
    }
    sizes = _apply_model(cfg, seed=11)
    assert all(size in {1.0, 10.0} for size in sizes)


def test_size_stats_by_label() -> None:
    particles = [
        {"label": "a", "size_um": 1.0},
        {"label": "a", "size_um": 2.0},
        {"label": "b", "size_um": 3.0},
    ]
    stats = compute_size_stats_by_label(particles, quantiles=[0.5])
    assert stats["a"]["count"] == 2
    assert stats["a"]["quantiles"]["p50"] == 1.5
    assert stats["b"]["mean"] == 3.0
