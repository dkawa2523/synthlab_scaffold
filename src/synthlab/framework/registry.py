from __future__ import annotations

import warnings
from typing import Any, Callable, Dict, Iterable, TYPE_CHECKING, Type

if TYPE_CHECKING:
    from .process import BaseProcess


_PROCESS_REGISTRY: Dict[str, "Type[BaseProcess]"] = {}
_PATTERN_REGISTRY: Dict[str, Callable[..., Any]] = {}
_SIZE_MODEL_REGISTRY: Dict[str, Callable[..., Any]] = {}
_METRIC_REGISTRY: Dict[str, Callable[..., Any]] = {}
_VISUALIZER_REGISTRY: Dict[str, Callable[..., Any]] = {}
_MODEL_REGISTRY: Dict[str, Callable[..., Any]] = {}


def _validate_namespaced_key(name: str, kind: str) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError(f"{kind} key must be a non-empty string")
    if name.strip() != name:
        raise ValueError(f"{kind} key must not contain leading/trailing whitespace: {name}")
    parts = name.split(".")
    if len(parts) < 3 or any(not part for part in parts):
        raise ValueError(
            f"{kind} key must be namespaced like 'domain.{kind}.name': {name}"
        )


def _register(mapping: Dict[str, Any], name: str, value: Any, kind: str) -> Any:
    _validate_namespaced_key(name, kind)
    if name in mapping:
        warnings.warn(f"{kind} already registered: {name}", RuntimeWarning, stacklevel=3)
        raise ValueError(f"{kind} already registered: {name}")
    mapping[name] = value
    return value


def _get(mapping: Dict[str, Any], name: str, kind: str) -> Any:
    if name not in mapping:
        known = ", ".join(sorted(mapping.keys()))
        raise KeyError(f"unknown {kind}: {name}. known=[{known}]")
    return mapping[name]


def register_process(name: str) -> Callable[["Type[BaseProcess]"], "Type[BaseProcess]"]:
    def _decorator(cls: "Type[BaseProcess]") -> "Type[BaseProcess]":
        return _register(_PROCESS_REGISTRY, name, cls, "process")

    return _decorator


def get_process(name: str) -> "Type[BaseProcess]":
    return _get(_PROCESS_REGISTRY, name, "process")


def list_processes() -> Iterable[str]:
    return sorted(_PROCESS_REGISTRY.keys())


def register_pattern(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return _register(_PATTERN_REGISTRY, name, func, "pattern")

    return _decorator


def get_pattern(name: str) -> Callable[..., Any]:
    return _get(_PATTERN_REGISTRY, name, "pattern")


def list_patterns() -> Iterable[str]:
    return sorted(_PATTERN_REGISTRY.keys())


def register_size_model(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return _register(_SIZE_MODEL_REGISTRY, name, func, "size_model")

    return _decorator


def get_size_model(name: str) -> Callable[..., Any]:
    return _get(_SIZE_MODEL_REGISTRY, name, "size_model")


def list_size_models() -> Iterable[str]:
    return sorted(_SIZE_MODEL_REGISTRY.keys())


def register_metric(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return _register(_METRIC_REGISTRY, name, func, "metric")

    return _decorator


def get_metric(name: str) -> Callable[..., Any]:
    return _get(_METRIC_REGISTRY, name, "metric")


def list_metrics() -> Iterable[str]:
    return sorted(_METRIC_REGISTRY.keys())


def register_visualizer(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return _register(_VISUALIZER_REGISTRY, name, func, "visualizer")

    return _decorator


def get_visualizer(name: str) -> Callable[..., Any]:
    return _get(_VISUALIZER_REGISTRY, name, "visualizer")


def list_visualizers() -> Iterable[str]:
    return sorted(_VISUALIZER_REGISTRY.keys())


def register_model(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def _decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return _register(_MODEL_REGISTRY, name, func, "model")

    return _decorator


def get_model(name: str) -> Callable[..., Any]:
    return _get(_MODEL_REGISTRY, name, "model")


def list_models() -> Iterable[str]:
    return sorted(_MODEL_REGISTRY.keys())
