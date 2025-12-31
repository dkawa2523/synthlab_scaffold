from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.domains.wafer_particles import param_space  # noqa: E402


def test_param_space_samples_valid_specs() -> None:
    rng = np.random.default_rng(123)
    specs = {
        "uniform": {"dist": "uniform", "low": 0.1, "high": 0.9},
        "loguniform": {"dist": "loguniform", "low": 1e-3, "high": 1e-1},
        "normal": {"dist": "normal", "mean": 0.0, "std": 1.0},
        "truncnorm": {"dist": "truncnorm", "mean": 0.0, "std": 1.0, "min": -1.0, "max": 1.0},
        "beta": {"dist": "beta", "alpha": 2.0, "beta": 5.0, "min": 0.0, "max": 1.0},
        "gamma": {"dist": "gamma", "shape": 2.0, "scale": 1.0},
        "vonmises": {"dist": "vonmises", "mu": 0.0, "kappa": 1.0},
        "choice": {"dist": "choice", "values": ["a", "b"], "weights": [0.2, 0.8]},
        "fixed": 0.5,
    }
    for name, spec in specs.items():
        value = param_space.sample_param_spec(spec, rng, f"specs.{name}")
        assert value is not None


def test_param_space_is_deterministic() -> None:
    spec = {"dist": "uniform", "low": 0.0, "high": 1.0}
    rng_a = np.random.default_rng(7)
    rng_b = np.random.default_rng(7)
    assert param_space.sample_param_spec(spec, rng_a, "uniform") == param_space.sample_param_spec(
        spec,
        rng_b,
        "uniform",
    )


def test_param_space_invalid_specs_raise() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        param_space.sample_param_spec({"dist": "mystery", "low": 0.0, "high": 1.0}, rng, "bad.dist")
    with pytest.raises(ValueError):
        param_space.sample_param_spec({"dist": "uniform", "low": 1.0, "high": 1.0}, rng, "bad.range")
    with pytest.raises(ValueError):
        param_space.sample_param_spec({"dist": "normal", "mean": 0.0}, rng, "bad.normal")
