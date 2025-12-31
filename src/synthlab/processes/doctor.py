from __future__ import annotations

import importlib
import math
import platform
import random
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Sequence

from synthlab.domains.wafer_particles import param_space
from synthlab.domains.wafer_particles.generators.patterns.catalog import load_pattern_catalog
from synthlab.domains.wafer_particles.generators.patterns.common import resolve_sample_ctx
from synthlab.domains.wafer_particles.labeling import LabelingSpec
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import get_pattern, register_process
from synthlab.processes._wafer_particles_io import resolve_path


def _torch_info() -> Dict[str, Any]:
    try:
        import torch
    except Exception as exc:  # pragma: no cover - optional dependency
        return {
            "available": False,
            "cuda_available": False,
            "error": str(exc),
        }
    return {
        "available": True,
        "version": getattr(torch, "__version__", "unknown"),
        "cuda_available": bool(torch.cuda.is_available()),
    }


def _module_info(name: str) -> Dict[str, Any]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # pragma: no cover - optional dependency
        return {
            "available": False,
            "error": str(exc),
        }
    version = getattr(module, "__version__", None)
    return {
        "available": True,
        "version": version or "unknown",
    }


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == "???"


def _resolve_process_name(cfg: Mapping[str, Any]) -> str | None:
    proc = cfg.get("process")
    if isinstance(proc, Mapping):
        return str(proc.get("name") or "")
    if isinstance(proc, str):
        return proc
    return None


def _resolve_domain_name(cfg: Mapping[str, Any]) -> str | None:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping):
        return str(domain.get("name") or "")
    if isinstance(domain, str):
        return domain
    return None


def _resolve_io_format(cfg: Mapping[str, Any]) -> str | None:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        return None
    io_cfg = wp_cfg.get("io")
    if not isinstance(io_cfg, Mapping):
        return None
    fmt = io_cfg.get("format")
    if fmt is None:
        return None
    return str(fmt).lower()


PATTERN_SCHEMA_VERSION = "wafer_particles.pattern_config.v1"
LABELING_SCHEMA_VERSION = "wafer_particles.labeling_spec.v1"
OPTIONAL_PATTERN_PREFIXES = ("O01", "O02")
KNOWN_SIZE_MODELS = {
    "wafer_particles.size_model.gaussian",
    "wafer_particles.size_model.lognormal",
    "wafer_particles.size_model.mixture",
}


def _read_mapping(value: Any, name: str, *, required: bool = False) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _is_optional_label(label: str) -> bool:
    upper = str(label).upper()
    return any(upper.startswith(prefix) for prefix in OPTIONAL_PATTERN_PREFIXES)


def _validate_positive_float(value: Any, name: str) -> None:
    if value is None:
        return
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")


def _coerce_positive_int(value: Any, name: str) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an int") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _has_range_keys(cfg: Mapping[str, Any]) -> bool:
    return any(key in cfg for key in ("min", "max", "low", "high", "start", "stop"))


def _has_keys(cfg: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return any(key in cfg and cfg.get(key) is not None for key in keys)


def _range_bounds(cfg: Mapping[str, Any], name: str) -> tuple[float, float]:
    min_value = cfg.get("min", cfg.get("low", cfg.get("start")))
    max_value = cfg.get("max", cfg.get("high", cfg.get("stop")))
    if min_value is None or max_value is None:
        raise ValueError(f"{name} requires min/max")
    min_value = float(min_value)
    max_value = float(max_value)
    if min_value > max_value:
        raise ValueError(f"{name} must satisfy min<=max")
    return min_value, max_value


def _validate_int_range(min_value: float, max_value: float, name: str) -> None:
    if max_value < 1:
        raise ValueError(f"{name} range must allow positive integers")
    min_int = int(math.ceil(min_value))
    max_int = int(math.floor(max_value))
    if min_int <= 0:
        min_int = 1
    if min_int > max_int:
        raise ValueError(f"{name} range must satisfy min<=max after integer coercion")


def _validate_n_particles_distribution(dist_cfg: Any, name: str) -> None:
    if dist_cfg is None:
        return
    if isinstance(dist_cfg, Mapping):
        cfg = dict(dist_cfg)
        dist_type = str(cfg.get("type") or cfg.get("mode") or "").lower()
        if not dist_type:
            if _has_range_keys(cfg):
                dist_type = "range"
            elif _has_keys(cfg, ("mean", "mu", "lambda")):
                dist_type = "poisson"
            elif _has_keys(cfg, ("n", "p")):
                dist_type = "negative_binomial"
            elif _has_keys(cfg, ("value", "count", "n_particles")):
                dist_type = "fixed"
        if dist_type in {"fixed", "value"} or not dist_type:
            value = cfg.get("value", cfg.get("count", cfg.get("n_particles")))
            _coerce_positive_int(value, f"{name}.value")
            return
        if dist_type in {"range", "uniform"}:
            min_value, max_value = _range_bounds(cfg, name)
            _validate_int_range(min_value, max_value, name)
            return
        if dist_type == "poisson":
            mean = cfg.get("mean", cfg.get("mu", cfg.get("lambda")))
            if mean is None:
                raise ValueError(f"{name}.mean is required")
            if float(mean) <= 0:
                raise ValueError(f"{name}.mean must be positive")
            return
        if dist_type in {"negative_binomial", "neg_binomial", "nb"}:
            mean = cfg.get("mean")
            dispersion = cfg.get("dispersion", cfg.get("r", cfg.get("k")))
            if mean is None or dispersion is None:
                n_value = cfg.get("n")
                p_value = cfg.get("p")
                if n_value is None or p_value is None:
                    raise ValueError(f"{name} requires mean+dispersion or n+p")
                n_value = float(n_value)
                p_value = float(p_value)
                if n_value <= 0 or p_value <= 0 or p_value >= 1:
                    raise ValueError(f"{name}.n must be positive and p in (0,1)")
            else:
                mean = float(mean)
                dispersion = float(dispersion)
                if mean <= 0 or dispersion <= 0:
                    raise ValueError(f"{name}.mean and dispersion must be positive")
            return
        raise ValueError(f"{name} has unsupported type: {dist_type}")
    if isinstance(dist_cfg, (list, tuple)):
        if len(dist_cfg) != 2:
            raise ValueError(f"{name} range must have 2 values")
        min_value = float(dist_cfg[0])
        max_value = float(dist_cfg[1])
        if min_value > max_value:
            raise ValueError(f"{name} range must satisfy min<=max")
        _validate_int_range(min_value, max_value, name)
        return
    _coerce_positive_int(dist_cfg, name)


def _validate_min_max(cfg: Mapping[str, Any], name: str) -> None:
    min_um = cfg.get("min_um")
    max_um = cfg.get("max_um")
    if min_um is None or max_um is None:
        return
    min_value = float(min_um)
    max_value = float(max_um)
    if max_value < min_value:
        raise ValueError(f"{name}.max_um must be >= min_um")


def _validate_size_model_cfg(cfg: Mapping[str, Any], name: str) -> None:
    model_name = cfg.get("name")
    if not model_name:
        raise ValueError(f"{name}.name is required")
    model_name = str(model_name)
    if model_name not in KNOWN_SIZE_MODELS:
        raise ValueError(f"{name}.name is not a known size model for doctor validation")
    if model_name == "wafer_particles.size_model.gaussian":
        _validate_min_max(cfg, name)
        std = float(cfg.get("std_um", 0.2))
        if std < 0:
            raise ValueError(f"{name}.std_um must be non-negative")
        float(cfg.get("mean_um", 1.0))
        return
    if model_name == "wafer_particles.size_model.lognormal":
        _validate_min_max(cfg, name)
        sigma = float(cfg.get("sigma_log", 0.25))
        if sigma < 0:
            raise ValueError(f"{name}.sigma_log must be non-negative")
        float(cfg.get("mu_log", 0.0))
        return
    if model_name == "wafer_particles.size_model.mixture":
        components = cfg.get("components")
        if not isinstance(components, list) or not components:
            raise ValueError(f"{name}.components must be a non-empty list")
        weights: list[float] = []
        for idx, component in enumerate(components):
            if not isinstance(component, Mapping):
                raise ValueError(f"{name}.components[{idx}] must be a mapping")
            weight = float(component.get("weight", 1.0))
            if weight < 0:
                raise ValueError(f"{name}.components[{idx}].weight must be non-negative")
            weights.append(weight)
            component_cfg = component.get("cfg") or {}
            if not isinstance(component_cfg, Mapping):
                raise ValueError(f"{name}.components[{idx}].cfg must be a mapping")
            component_cfg = dict(component_cfg)
            model_override = component_cfg.get("name") or component.get("model") or component.get("name")
            if not model_override:
                raise ValueError(f"{name}.components[{idx}] requires model/name")
            component_cfg["name"] = str(model_override)
            _validate_size_model_cfg(component_cfg, f"{name}.components[{idx}]")
        total = sum(weights)
        if total <= 0:
            raise ValueError(f"{name}.components weights must sum to > 0")
        return


def _collect_optional_labels_from_selection(selection_cfg: Any) -> list[str]:
    if not isinstance(selection_cfg, Mapping):
        return []
    labels: list[str] = []
    labels_raw = selection_cfg.get("labels")
    if isinstance(labels_raw, list):
        labels.extend([str(item) for item in labels_raw])
    ratios = selection_cfg.get("ratios")
    if isinstance(ratios, Mapping):
        labels.extend([str(item) for item in ratios.keys()])
    return [label for label in labels if _is_optional_label(label)]


def _warn_ratio_bounds(
    cfg: Mapping[str, Any],
    path: str,
    add_check,
) -> None:
    for key, value in cfg.items():
        key_path = f"{path}.{key}"
        if isinstance(value, Mapping):
            if key.endswith("_ratio") and "dist" in value:
                low = value.get("min", value.get("low"))
                high = value.get("max", value.get("high"))
                try:
                    low_val = float(low) if low is not None else None
                    high_val = float(high) if high is not None else None
                except (TypeError, ValueError):
                    continue
                if (low_val is not None and low_val < 0) or (high_val is not None and high_val > 1):
                    add_check(key_path, "warn", "ratio bounds should be within 0..1", value=value)
            _warn_ratio_bounds(value, key_path, add_check)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, Mapping):
                    _warn_ratio_bounds(item, f"{key_path}[{idx}]", add_check)
        else:
            if not key.endswith("_ratio") or value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric < 0 or numeric > 1:
                add_check(key_path, "warn", "ratio should be within 0..1", value=numeric)


def _norm_from_cfg(cfg: Mapping[str, Any], norm_key: str, ratio_key: str, mm_key: str) -> float | None:
    if norm_key in cfg:
        return float(cfg[norm_key])
    if ratio_key in cfg:
        return float(cfg[ratio_key])
    if mm_key in cfg:
        wafer_radius_mm = cfg.get("wafer_radius_mm")
        if wafer_radius_mm:
            return float(cfg[mm_key]) / float(wafer_radius_mm)
    return None


def _check_core_pattern_constraints(label_name: str, cfg: Mapping[str, Any], add_check) -> None:
    if label_name == "C04_Sector_Edge":
        edge_width = _norm_from_cfg(cfg, "edge_width_norm", "edge_width_ratio", "edge_width_mm")
        if edge_width is not None and edge_width <= 0:
            add_check(
                "wafer_particles.patterns.C04_Sector_Edge.edge_width_norm",
                "error",
                "edge_width must be positive",
                value=edge_width,
            )
    if label_name == "C05_Sector_Internal":
        margin = _norm_from_cfg(cfg, "edge_margin_norm", "edge_margin_ratio", "edge_margin_mm")
        if margin is None:
            margin = 0.05
        r_outer = _norm_from_cfg(cfg, "r_outer_norm", "r_outer_ratio", "r_outer_mm")
        if r_outer is not None and r_outer > 1.0 - margin:
            add_check(
                "wafer_particles.patterns.C05_Sector_Internal.r_outer_norm",
                "error",
                "r_outer exceeds edge margin for internal sector",
                value=r_outer,
            )
        r_inner = _norm_from_cfg(cfg, "r_inner_norm", "r_inner_ratio", "r_inner_mm")
        if r_inner is not None and r_outer is not None and r_inner >= r_outer:
            add_check(
                "wafer_particles.patterns.C05_Sector_Internal.r_inner_norm",
                "error",
                "r_inner must be < r_outer",
                value=r_inner,
            )
    if label_name == "C12_Crescent_Edge":
        margin = _norm_from_cfg(cfg, "edge_margin_norm", "edge_margin_ratio", "edge_margin_mm")
        if margin is None:
            margin = 0.02
        outer_radius = _norm_from_cfg(cfg, "outer_radius_norm", "outer_radius_ratio", "outer_radius_mm")
        if outer_radius is not None and outer_radius < 1.0 - margin:
            add_check(
                "wafer_particles.patterns.C12_Crescent_Edge.outer_radius_norm",
                "error",
                "outer_radius does not reach edge margin",
                value=outer_radius,
            )
    if label_name == "C13_Crescent_Internal":
        margin = _norm_from_cfg(cfg, "edge_margin_norm", "edge_margin_ratio", "edge_margin_mm")
        if margin is None:
            margin = 0.05
        outer_radius = _norm_from_cfg(cfg, "outer_radius_norm", "outer_radius_ratio", "outer_radius_mm")
        if outer_radius is not None and outer_radius > 1.0 - margin:
            add_check(
                "wafer_particles.patterns.C13_Crescent_Internal.outer_radius_norm",
                "error",
                "outer_radius exceeds edge margin for internal crescent",
                value=outer_radius,
            )


@register_process("wafer_particles.process.doctor")
class DoctorProcess(BaseProcess):
    name = "wafer_particles.process.doctor"

    def run(self, writer) -> None:
        writer.log("doctor start")
        checks: list[dict[str, Any]] = []

        def add_check(name: str, status: str, message: str, *, value: Any | None = None) -> None:
            entry = {"name": name, "status": status, "message": message}
            if value is not None:
                entry["value"] = value
            checks.append(entry)

        cfg = self.cfg
        seed = cfg.get("seed")
        if _is_missing(seed):
            add_check("config.seed", "error", "seed is required for determinism")
        else:
            try:
                seed_value = int(seed)
            except (TypeError, ValueError):
                add_check("config.seed", "error", "seed must be an int")
            else:
                add_check("config.seed", "ok", "seed is set", value=seed_value)

        schema_version = cfg.get("schema_version")
        if _is_missing(schema_version):
            add_check("config.schema_version", "error", "schema_version is required")
        else:
            add_check("config.schema_version", "ok", "schema_version is set", value=str(schema_version))

        run_name = cfg.get("run_name")
        if _is_missing(run_name):
            add_check("config.run_name", "error", "run_name is required")
        else:
            add_check("config.run_name", "ok", "run_name is set", value=str(run_name))

        process_name = _resolve_process_name(cfg)
        if _is_missing(process_name):
            add_check("config.process", "error", "process.name is required")
        else:
            add_check("config.process", "ok", "process is set", value=str(process_name))

        domain_name = _resolve_domain_name(cfg)
        if _is_missing(domain_name):
            add_check("config.domain", "error", "domain.name is required")
        else:
            add_check("config.domain", "ok", "domain is set", value=str(domain_name))

        dependencies = {
            "pyarrow": _module_info("pyarrow"),
            "matplotlib": _module_info("matplotlib"),
            "yaml": _module_info("yaml"),
            "torch": _torch_info(),
        }

        io_format = _resolve_io_format(cfg)
        if io_format == "parquet":
            if not dependencies["pyarrow"]["available"]:
                add_check(
                    "dependency.pyarrow",
                    "error",
                    "pyarrow is required for parquet I/O (use wafer_particles.io.format=csv).",
                )
            else:
                add_check("dependency.pyarrow", "ok", "pyarrow available for parquet")
        elif io_format == "csv":
            add_check("dependency.pyarrow", "ok", "csv selected; pyarrow optional")
        elif io_format == "auto":
            if dependencies["pyarrow"]["available"]:
                add_check("dependency.pyarrow", "ok", "auto selected; parquet available")
            else:
                add_check("dependency.pyarrow", "ok", "auto selected; falling back to csv")

        if process_name == "wafer_particles.process.viz":
            if not dependencies["matplotlib"]["available"]:
                add_check("dependency.matplotlib", "error", "matplotlib is required for viz process")
            else:
                add_check("dependency.matplotlib", "ok", "matplotlib available for viz")
        else:
            if not dependencies["matplotlib"]["available"]:
                add_check("dependency.matplotlib", "warn", "matplotlib not installed (viz will fail)")

        wp_cfg_raw = cfg.get("wafer_particles")
        optional_labels: list[str] = []
        if not isinstance(wp_cfg_raw, Mapping):
            add_check("config.wafer_particles", "error", "wafer_particles config is required")
        else:
            wp_cfg = dict(wp_cfg_raw)
            try:
                _validate_positive_float(wp_cfg.get("wafer_radius_mm"), "wafer_particles.wafer_radius_mm")
            except ValueError as exc:
                add_check("wafer_particles.wafer_radius_mm", "error", str(exc))
            try:
                _validate_n_particles_distribution(
                    wp_cfg.get("n_particles_distribution"),
                    "wafer_particles.n_particles_distribution",
                )
            except ValueError as exc:
                add_check("wafer_particles.n_particles_distribution", "error", str(exc))

            patterns = wp_cfg.get("patterns")
            if patterns is None:
                add_check("wafer_particles.patterns", "error", "wafer_particles.patterns config is required")
            elif not isinstance(patterns, Mapping):
                add_check("wafer_particles.patterns", "error", "wafer_particles.patterns must be a mapping")
            else:
                for label, pattern_cfg in patterns.items():
                    label_name = str(label)
                    if _is_optional_label(label_name):
                        optional_labels.append(label_name)
                    if not isinstance(pattern_cfg, Mapping):
                        add_check(
                            f"wafer_particles.patterns.{label_name}",
                            "error",
                            "pattern config must be a mapping",
                        )
                        continue
                    if not pattern_cfg.get("name"):
                        add_check(
                            f"wafer_particles.patterns.{label_name}.name",
                            "error",
                            "pattern name is required",
                        )
                    schema_ver = pattern_cfg.get("schema_version")
                    if schema_ver is None:
                        add_check(
                            f"wafer_particles.patterns.{label_name}.schema_version",
                            "warn",
                            f"schema_version missing (expected {PATTERN_SCHEMA_VERSION})",
                        )
                    elif str(schema_ver) != PATTERN_SCHEMA_VERSION:
                        add_check(
                            f"wafer_particles.patterns.{label_name}.schema_version",
                            "warn",
                            f"schema_version mismatch (expected {PATTERN_SCHEMA_VERSION})",
                            value=str(schema_ver),
                        )
                    try:
                        param_space.validate_param_specs_in_config(
                            pattern_cfg,
                            path=f"wafer_particles.patterns.{label_name}",
                        )
                    except ValueError as exc:
                        add_check(
                            f"wafer_particles.patterns.{label_name}.param_space",
                            "error",
                            str(exc),
                        )
                    _warn_ratio_bounds(pattern_cfg, f"wafer_particles.patterns.{label_name}", add_check)
                    _check_core_pattern_constraints(label_name, pattern_cfg, add_check)
                    try:
                        _validate_n_particles_distribution(
                            pattern_cfg.get("n_particles_distribution"),
                            f"wafer_particles.patterns.{label_name}.n_particles_distribution",
                        )
                    except ValueError as exc:
                        add_check(
                            f"wafer_particles.patterns.{label_name}.n_particles_distribution",
                            "error",
                            str(exc),
                        )
                    if pattern_cfg.get("n_particles") is not None:
                        try:
                            _coerce_positive_int(
                                pattern_cfg.get("n_particles"),
                                f"wafer_particles.patterns.{label_name}.n_particles",
                            )
                        except ValueError as exc:
                            add_check(
                                f"wafer_particles.patterns.{label_name}.n_particles",
                                "error",
                                str(exc),
                            )
                    try:
                        _validate_positive_float(
                            pattern_cfg.get("wafer_radius_mm"),
                            f"wafer_particles.patterns.{label_name}.wafer_radius_mm",
                        )
                    except ValueError as exc:
                        add_check(
                            f"wafer_particles.patterns.{label_name}.wafer_radius_mm",
                            "error",
                            str(exc),
                        )

                try:
                    catalog = load_pattern_catalog(wp_cfg, warn=lambda msg: add_check("wafer_particles.patterns.warn", "warn", msg))
                except ValueError as exc:
                    add_check("wafer_particles.patterns.catalog", "error", str(exc))
                else:
                    sample_ctx = {
                        "n_particles": int(wp_cfg.get("n_particles", 16) or 16),
                        "wafer_radius_mm": wp_cfg.get("wafer_radius_mm"),
                    }
                    for label, entry in catalog.enabled_entries().items():
                        try:
                            generator = get_pattern(entry.pattern_id)
                            ctx = resolve_sample_ctx(entry.cfg, sample_ctx)
                            rng = random.Random(0)
                            if hasattr(generator, "generate"):
                                particles = generator.generate(ctx, entry.cfg, rng)
                            else:
                                particles = generator(entry.cfg, rng, sample_ctx)
                            valid = True
                            for particle in particles:
                                r_norm = particle.get("r_norm")
                                if r_norm is None and particle.get("r_mm") is not None:
                                    r_norm = float(particle["r_mm"]) / ctx.wafer_radius_mm
                                if r_norm is None or r_norm < -1e-6 or r_norm > 1.0 + 1e-6:
                                    valid = False
                                    break
                            if valid:
                                add_check(
                                    f"wafer_particles.patterns.{label}.bounds",
                                    "ok",
                                    "pattern bounds ok",
                                )
                            else:
                                add_check(
                                    f"wafer_particles.patterns.{label}.bounds",
                                    "error",
                                    "pattern produced out-of-bounds particle",
                                )
                        except Exception as exc:
                            add_check(
                                f"wafer_particles.patterns.{label}.bounds",
                                "error",
                                f"pattern validation failed: {exc}",
                            )

            size_cfg = wp_cfg.get("size_models") or wp_cfg.get("size_model")
            if size_cfg is None:
                add_check("wafer_particles.size_models", "error", "wafer_particles.size_models config is required")
            elif not isinstance(size_cfg, Mapping):
                add_check("wafer_particles.size_models", "error", "wafer_particles.size_models must be a mapping")
            else:
                try:
                    param_space.validate_param_specs_in_config(size_cfg, path="wafer_particles.size_models")
                except ValueError as exc:
                    add_check("wafer_particles.size_models.param_space", "error", str(exc))
                try:
                    _validate_size_model_cfg(size_cfg, "wafer_particles.size_models")
                except ValueError as exc:
                    status = "warn" if "not a known size model" in str(exc) else "error"
                    add_check("wafer_particles.size_models", status, str(exc))
                by_label = size_cfg.get("by_label")
                if by_label is not None:
                    if not isinstance(by_label, Mapping):
                        add_check(
                            "wafer_particles.size_models.by_label",
                            "error",
                            "wafer_particles.size_models.by_label must be a mapping",
                        )
                    else:
                        for label, override in by_label.items():
                            if not isinstance(override, Mapping):
                                add_check(
                                    f"wafer_particles.size_models.by_label.{label}",
                                    "error",
                                    "label size model config must be a mapping",
                                )
                                continue
                            merged = dict(size_cfg)
                            merged.pop("by_label", None)
                            merged.update(override)
                            try:
                                _validate_size_model_cfg(
                                    merged,
                                    f"wafer_particles.size_models.by_label.{label}",
                                )
                            except ValueError as exc:
                                status = "warn" if "not a known size model" in str(exc) else "error"
                                add_check(
                                    f"wafer_particles.size_models.by_label.{label}",
                                    status,
                                    str(exc),
                                )

            labeling_cfg = wp_cfg.get("labeling")
            if labeling_cfg is not None:
                if not isinstance(labeling_cfg, Mapping):
                    add_check(
                        "wafer_particles.labeling",
                        "error",
                        "wafer_particles.labeling must be a mapping",
                    )
                else:
                    spec_path = labeling_cfg.get("spec_path")
                    if not spec_path:
                        add_check(
                            "wafer_particles.labeling.spec_path",
                            "error",
                            "wafer_particles.labeling.spec_path is required",
                        )
                    else:
                        resolved = resolve_path(spec_path, writer.repo_root)
                        if not resolved.exists():
                            add_check(
                                "wafer_particles.labeling.spec_path",
                                "error",
                                f"labeling spec not found: {resolved}",
                            )
                        else:
                            try:
                                spec = LabelingSpec.load(resolved)
                            except Exception as exc:
                                add_check(
                                    "wafer_particles.labeling.spec_path",
                                    "error",
                                    f"failed to load labeling spec: {exc}",
                                )
                            else:
                                labeling_schema = spec.raw.get("schema_version")
                                if labeling_schema is None:
                                    add_check(
                                        "wafer_particles.labeling.schema_version",
                                        "warn",
                                        f"schema_version missing (expected {LABELING_SCHEMA_VERSION})",
                                    )
                                elif str(labeling_schema) != LABELING_SCHEMA_VERSION:
                                    add_check(
                                        "wafer_particles.labeling.schema_version",
                                        "warn",
                                        f"schema_version mismatch (expected {LABELING_SCHEMA_VERSION})",
                                        value=str(labeling_schema),
                                    )

            optional_labels.extend(_collect_optional_labels_from_selection(wp_cfg.get("label_selection")))
            optional_labels = sorted(set(optional_labels))
            if optional_labels and not bool(wp_cfg.get("allow_optional_patterns", False)):
                add_check(
                    "wafer_particles.patterns.optional",
                    "warn",
                    "optional patterns enabled without allow_optional_patterns=true",
                    value=optional_labels,
                )

        ok = not any(check["status"] == "error" for check in checks)
        payload = {
            "ok": ok,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "python": {
                "version": sys.version.split()[0],
                "executable": sys.executable,
            },
            "platform": platform.platform(),
            "dependencies": dependencies,
            "config": {
                "run_name": run_name,
                "process_name": process_name,
                "domain": domain_name,
                "schema_version": schema_version,
                "seed": seed,
                "io_format": io_format,
            },
            "checks": checks,
        }
        writer.write_json("meta/doctor.json", payload)
        if not ok:
            errors = [f"{check['name']}: {check['message']}" for check in checks if check["status"] == "error"]
            writer.log("doctor failed")
            raise ValueError("doctor validation failed: " + "; ".join(errors))
        writer.log("doctor complete")
