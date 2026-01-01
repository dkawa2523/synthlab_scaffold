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


def _apply_sizes(cfg: dict[str, object], seed: int = 7) -> list[float]:
    rng = random.Random(seed)
    particles = [{"label": "default"} for _ in range(12)]
    apply_size_model(cfg, rng, particles)
    return [float(particle["size_um"]) for particle in particles]


@pytest.mark.parametrize(
    "cfg",
    [
        {
            "type": "lognormal",
            "mu_log": 2.0,
            "sigma_log": 0.3,
            "min_um": 0.05,
            "max_um": 0.2,
        },
        {
            "type": "weibull",
            "k": 1.4,
            "lambda_um": 0.5,
            "min_um": 0.05,
            "max_um": 0.2,
        },
        {
            "type": "pareto",
            "alpha": 2.2,
            "xm_um": 0.4,
            "min_um": 0.05,
            "max_um": 0.2,
        },
    ],
)
def test_T0701_new_size_models_are_positive_and_clamped(cfg: dict[str, object]) -> None:
    sizes = _apply_sizes(cfg)
    min_um = float(cfg["min_um"])
    max_um = float(cfg["max_um"])
    assert all(size > 0 for size in sizes)
    assert all(min_um <= size <= max_um for size in sizes)
