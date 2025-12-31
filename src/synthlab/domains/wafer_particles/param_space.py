from __future__ import annotations

import hashlib
import random
from typing import Any, Mapping, Sequence

import numpy as np

RANGE_KEYS = ("min", "max", "low", "high", "start", "stop")


def numpy_rng_from_random(rng: random.Random) -> np.random.Generator:
    state = rng.getstate()
    payload = repr(state).encode("utf-8")
    seed = int(hashlib.sha256(payload).hexdigest()[:16], 16)
    return np.random.default_rng(seed)


def validate_param_spec(
    spec: Any,
    name: str,
    *,
    base_value: Any | None = None,
    allow_legacy_range: bool = False,
) -> None:
    if spec is None:
        if base_value is None:
            raise ValueError(f"{name} is required")
        return
    if isinstance(spec, Mapping):
        if "dist" in spec:
            _validate_dist_spec(spec, name)
            return
        if allow_legacy_range and _has_range_keys(spec):
            _range_bounds(spec, name)
            return
        raise ValueError(f"{name} must be a fixed value or dist spec")
    if allow_legacy_range and isinstance(spec, (list, tuple)):
        _validate_range_list(spec, name)
        return
    if isinstance(spec, (str, int, float, bool, np.generic)):
        return
    raise ValueError(f"{name} must be a fixed value or dist spec")


def sample_param_spec(
    spec: Any,
    rng: np.random.Generator,
    name: str,
    *,
    base_value: Any | None = None,
    allow_legacy_range: bool = False,
) -> Any:
    validate_param_spec(spec, name, base_value=base_value, allow_legacy_range=allow_legacy_range)
    if spec is None:
        return base_value
    if isinstance(spec, Mapping):
        if "dist" in spec:
            sampled = _sample_dist_spec(spec, rng, name)
            if isinstance(sampled, (int, float, np.generic)):
                return _coerce_numeric(float(sampled), base_value)
            return sampled
        if allow_legacy_range and _has_range_keys(spec):
            low, high = _range_bounds(spec, name)
            return _coerce_numeric(float(rng.uniform(low, high)), base_value)
        return spec
    if allow_legacy_range and isinstance(spec, (list, tuple)):
        low, high = _range_list_bounds(spec, name)
        return _coerce_numeric(float(rng.uniform(low, high)), base_value)
    return spec


def apply_param_space(
    cfg: Mapping[str, Any],
    rng: np.random.Generator,
    *,
    path: str = "",
    param_space_key: str = "param_space",
    param_ranges_key: str = "param_ranges",
) -> None:
    if not isinstance(cfg, Mapping):
        raise ValueError(f"{path or 'param_space'} must be a mapping")
    if param_space_key in cfg:
        _apply_param_map(cfg, rng, param_space_key, path, allow_legacy_range=True)
    if param_ranges_key in cfg:
        _apply_param_map(cfg, rng, param_ranges_key, path, allow_legacy_range=True)

    for key, value in list(cfg.items()):
        if key in {param_space_key, param_ranges_key}:
            continue
        key_path = _join_path(path, str(key))
        if isinstance(value, Mapping):
            if "dist" in value:
                cfg[key] = sample_param_spec(value, rng, key_path)
            else:
                apply_param_space(value, rng, path=key_path)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                item_path = f"{key_path}[{idx}]"
                if isinstance(item, Mapping):
                    if "dist" in item:
                        value[idx] = sample_param_spec(item, rng, item_path)
                    else:
                        apply_param_space(item, rng, path=item_path)


def validate_param_specs_in_config(
    cfg: Mapping[str, Any],
    *,
    path: str = "",
    param_space_key: str = "param_space",
    param_ranges_key: str = "param_ranges",
) -> None:
    if not isinstance(cfg, Mapping):
        raise ValueError(f"{path or 'param_space'} must be a mapping")
    if param_space_key in cfg:
        _validate_param_map(cfg, param_space_key, path, allow_legacy_range=True)
    if param_ranges_key in cfg:
        _validate_param_map(cfg, param_ranges_key, path, allow_legacy_range=True)
    for key, value in cfg.items():
        if key in {param_space_key, param_ranges_key}:
            continue
        key_path = _join_path(path, str(key))
        if isinstance(value, Mapping):
            if "dist" in value:
                validate_param_spec(value, key_path)
            else:
                validate_param_specs_in_config(value, path=key_path)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                item_path = f"{key_path}[{idx}]"
                if isinstance(item, Mapping):
                    if "dist" in item:
                        validate_param_spec(item, item_path)
                    else:
                        validate_param_specs_in_config(item, path=item_path)


def _apply_param_map(
    cfg: Mapping[str, Any],
    rng: np.random.Generator,
    key: str,
    path: str,
    *,
    allow_legacy_range: bool,
) -> None:
    space = cfg.get(key)
    if not isinstance(space, Mapping):
        raise ValueError(f"{_join_path(path, key)} must be a mapping")
    for param_key, spec in space.items():
        base_value = cfg.get(param_key)
        param_path = _join_path(_join_path(path, key), str(param_key))
        cfg[str(param_key)] = sample_param_spec(
            spec,
            rng,
            param_path,
            base_value=base_value,
            allow_legacy_range=allow_legacy_range,
        )
    cfg.pop(key, None)


def _validate_param_map(
    cfg: Mapping[str, Any],
    key: str,
    path: str,
    *,
    allow_legacy_range: bool,
) -> None:
    space = cfg.get(key)
    if not isinstance(space, Mapping):
        raise ValueError(f"{_join_path(path, key)} must be a mapping")
    for param_key, spec in space.items():
        base_value = cfg.get(param_key)
        param_path = _join_path(_join_path(path, key), str(param_key))
        validate_param_spec(spec, param_path, base_value=base_value, allow_legacy_range=allow_legacy_range)


def _validate_dist_spec(spec: Mapping[str, Any], name: str) -> None:
    dist = str(spec.get("dist") or "").lower()
    if not dist:
        raise ValueError(f"{name}.dist is required")
    if dist == "uniform":
        _require_range(spec, name, require_positive=False)
        return
    if dist == "loguniform":
        low, high = _require_range(spec, name, require_positive=True)
        if low <= 0 or high <= 0:
            raise ValueError(f"{name} requires low/high > 0 for loguniform")
        return
    if dist == "normal":
        mean = _require_numeric(spec, name, "mean")
        std = _require_numeric(spec, name, "std")
        if std < 0:
            raise ValueError(f"{name}.std must be non-negative")
        min_value = _optional_numeric(spec, "min")
        max_value = _optional_numeric(spec, "max")
        _validate_optional_bounds(name, min_value, max_value)
        if std == 0 and min_value is not None and max_value is not None:
            if not (min_value <= mean <= max_value):
                raise ValueError(f"{name}.mean must be within min/max when std=0")
        return
    if dist == "truncnorm":
        _require_numeric(spec, name, "mean")
        std = _require_numeric(spec, name, "std")
        if std <= 0:
            raise ValueError(f"{name}.std must be positive for truncnorm")
        min_value = _require_numeric(spec, name, "min")
        max_value = _require_numeric(spec, name, "max")
        if min_value >= max_value:
            raise ValueError(f"{name} requires min < max")
        return
    if dist == "beta":
        alpha = _require_numeric(spec, name, "alpha")
        beta = _require_numeric(spec, name, "beta")
        if alpha <= 0 or beta <= 0:
            raise ValueError(f"{name}.alpha and {name}.beta must be positive")
        min_value = _optional_numeric(spec, "min")
        max_value = _optional_numeric(spec, "max")
        _validate_optional_bounds(name, min_value, max_value)
        return
    if dist == "gamma":
        shape, scale = _resolve_gamma_params(spec, name)
        if shape <= 0 or scale <= 0:
            raise ValueError(f"{name}.shape and {name}.scale must be positive")
        return
    if dist == "vonmises":
        _require_numeric(spec, name, "mu")
        kappa = _require_numeric(spec, name, "kappa")
        if kappa < 0:
            raise ValueError(f"{name}.kappa must be non-negative")
        return
    if dist == "choice":
        _validate_choice_spec(spec, name)
        return
    raise ValueError(f"{name} has unsupported dist: {dist}")


def _sample_dist_spec(
    spec: Mapping[str, Any],
    rng: np.random.Generator,
    name: str,
) -> Any:
    dist = str(spec.get("dist") or "").lower()
    if dist == "uniform":
        low, high = _require_range(spec, name, require_positive=False)
        return float(rng.uniform(low, high))
    if dist == "loguniform":
        low, high = _require_range(spec, name, require_positive=True)
        return float(np.exp(rng.uniform(np.log(low), np.log(high))))
    if dist == "normal":
        mean = _require_numeric(spec, name, "mean")
        std = _require_numeric(spec, name, "std")
        value = float(rng.normal(mean, std))
        min_value = _optional_numeric(spec, "min")
        max_value = _optional_numeric(spec, "max")
        return _apply_bounds(value, min_value, max_value)
    if dist == "truncnorm":
        mean = _require_numeric(spec, name, "mean")
        std = _require_numeric(spec, name, "std")
        min_value = _require_numeric(spec, name, "min")
        max_value = _require_numeric(spec, name, "max")
        return _sample_truncnorm(rng, mean, std, min_value, max_value, name)
    if dist == "beta":
        alpha = _require_numeric(spec, name, "alpha")
        beta = _require_numeric(spec, name, "beta")
        min_value = _optional_numeric(spec, "min")
        max_value = _optional_numeric(spec, "max")
        if min_value is None:
            min_value = 0.0
        if max_value is None:
            max_value = 1.0
        value = float(rng.beta(alpha, beta))
        return min_value + value * (max_value - min_value)
    if dist == "gamma":
        shape, scale = _resolve_gamma_params(spec, name)
        return float(rng.gamma(shape, scale))
    if dist == "vonmises":
        mu = _require_numeric(spec, name, "mu")
        kappa = _require_numeric(spec, name, "kappa")
        return float(rng.vonmises(mu, kappa))
    if dist == "choice":
        values, weights = _choice_values_weights(spec, name)
        if weights is None:
            return values[int(rng.integers(0, len(values)))]
        return values[int(rng.choice(len(values), p=weights))]
    raise ValueError(f"{name} has unsupported dist: {dist}")


def _resolve_gamma_params(spec: Mapping[str, Any], name: str) -> tuple[float, float]:
    shape = spec.get("shape")
    scale = spec.get("scale")
    if shape is None and scale is None:
        shape = spec.get("k")
        scale = spec.get("theta")
    if shape is None or scale is None:
        raise ValueError(f"{name} requires shape+scale or k+theta")
    return float(shape), float(scale)


def _choice_values_weights(spec: Mapping[str, Any], name: str) -> tuple[list[Any], list[float] | None]:
    values = spec.get("values")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{name}.values must be a list")
    values_list = list(values)
    if not values_list:
        raise ValueError(f"{name}.values must be non-empty")
    weights = spec.get("weights")
    if weights is None:
        return values_list, None
    if not isinstance(weights, Sequence) or isinstance(weights, (str, bytes)):
        raise ValueError(f"{name}.weights must be a list")
    weights_list = [float(w) for w in weights]
    if len(weights_list) != len(values_list):
        raise ValueError(f"{name}.weights must match values length")
    if any(weight < 0 for weight in weights_list):
        raise ValueError(f"{name}.weights must be non-negative")
    total = sum(weights_list)
    if total <= 0:
        raise ValueError(f"{name}.weights must sum to > 0")
    normed = [weight / total for weight in weights_list]
    return values_list, normed


def _validate_choice_spec(spec: Mapping[str, Any], name: str) -> None:
    _choice_values_weights(spec, name)


def _require_numeric(spec: Mapping[str, Any], name: str, key: str) -> float:
    value = spec.get(key)
    if value is None:
        raise ValueError(f"{name}.{key} is required")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}.{key} must be numeric") from exc


def _optional_numeric(spec: Mapping[str, Any], key: str) -> float | None:
    if key not in spec or spec.get(key) is None:
        return None
    try:
        return float(spec[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc


def _validate_optional_bounds(name: str, min_value: float | None, max_value: float | None) -> None:
    if min_value is None or max_value is None:
        return
    if min_value >= max_value:
        raise ValueError(f"{name} requires min < max")


def _sample_truncnorm(
    rng: np.random.Generator,
    mean: float,
    std: float,
    min_value: float,
    max_value: float,
    name: str,
    *,
    max_attempts: int = 512,
) -> float:
    if std <= 0:
        if min_value <= mean <= max_value:
            return float(mean)
        raise ValueError(f"{name}.mean must be within min/max when std=0")
    for _ in range(max_attempts):
        value = float(rng.normal(mean, std))
        if min_value <= value <= max_value:
            return value
    raise ValueError(f"{name} truncnorm failed to sample within bounds after {max_attempts} attempts")


def _require_range(
    spec: Mapping[str, Any],
    name: str,
    *,
    require_positive: bool,
) -> tuple[float, float]:
    low, high = _range_bounds(spec, name)
    if low >= high:
        raise ValueError(f"{name} requires low < high")
    if require_positive and (low <= 0 or high <= 0):
        raise ValueError(f"{name} requires low/high > 0")
    return low, high


def _range_bounds(spec: Mapping[str, Any], name: str) -> tuple[float, float]:
    low = spec.get("low", spec.get("min", spec.get("start")))
    high = spec.get("high", spec.get("max", spec.get("stop")))
    if low is None or high is None:
        raise ValueError(f"{name} requires low/high")
    try:
        low_value = float(low)
        high_value = float(high)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} low/high must be numeric") from exc
    if low_value >= high_value:
        raise ValueError(f"{name} requires low < high")
    return low_value, high_value


def _validate_range_list(spec: Sequence[Any], name: str) -> None:
    if len(spec) != 2:
        raise ValueError(f"{name} range must have 2 values")
    _range_list_bounds(spec, name)


def _range_list_bounds(spec: Sequence[Any], name: str) -> tuple[float, float]:
    try:
        low = float(spec[0])
        high = float(spec[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} range values must be numeric") from exc
    if low >= high:
        raise ValueError(f"{name} requires low < high")
    return low, high


def _has_range_keys(spec: Mapping[str, Any]) -> bool:
    return any(key in spec for key in RANGE_KEYS)


def _coerce_numeric(value: float, base_value: Any | None) -> float | int:
    if base_value is None:
        return float(value)
    if isinstance(base_value, (bool, np.bool_)):
        return float(value)
    if isinstance(base_value, (int, np.integer)):
        return int(round(value))
    return float(value)


def _apply_bounds(value: float, min_value: float | None, max_value: float | None) -> float:
    if min_value is not None and value < min_value:
        return float(min_value)
    if max_value is not None and value > max_value:
        return float(max_value)
    return float(value)


def _join_path(base: str, key: str) -> str:
    if not base:
        return key
    return f"{base}.{key}"
