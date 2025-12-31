from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import random
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    polar_to_cartesian_mm,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles import param_space
from synthlab.domains.wafer_particles.generators.patterns.base import PatternContext
from synthlab.domains.wafer_particles.generators.patterns.catalog import load_pattern_catalog
from synthlab.domains.wafer_particles.generators.patterns.common import (
    norm_to_mm,
    resolve_sample_ctx,
    sample_poisson,
)
from synthlab.domains.wafer_particles.generators.size_models.common import apply_size_model
from synthlab.domains.wafer_particles.metrics.qc_metrics import (
    _compute_hist,
    _nearest_neighbor_distances,
    _resolve_edges,
)
from synthlab.domains.wafer_particles.noise import (
    apply_position_jitter,
    generate_background_particles,
    resolve_background_count,
)
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import get_pattern, register_process
from synthlab.processes._wafer_particles_io import (
    InputPaths,
    input_payload,
    read_table,
    resolve_input_paths,
    resolve_path,
)

import synthlab.domains.wafer_particles.generators  # noqa: F401


@dataclass(frozen=True)
class RealInput:
    particles: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    input_payload: dict[str, Any]
    input_config: dict[str, Any] | None
    samples_generated: bool


@dataclass(frozen=True)
class TrialResult:
    trial: int
    trial_type: str
    seed: int
    params: dict[str, Any]
    score: float
    metrics: dict[str, Any]
    n_particles: int
    n_samples: int


@dataclass(frozen=True)
class ParamSpec:
    name: str
    path: str
    min_value: float | None
    max_value: float | None
    values: list[Any] | None
    dtype: str | None
    base_value: Any


_MISSING = object()


@register_process("wafer_particles.process.calibrate_search")
class CalibrateSearchProcess(BaseProcess):
    name = "wafer_particles.process.calibrate_search"

    def run(self, writer) -> None:
        writer.log("calibrate_search start")
        cfg = self.cfg
        wp_cfg = _resolve_wafer_particles_cfg(cfg)
        cal_cfg = _read_mapping(
            wp_cfg.get("calibrate_search"),
            "wafer_particles.calibrate_search",
        )
        real_cfg = _read_mapping(
            cal_cfg.get("real"),
            "wafer_particles.calibrate_search.real",
        )
        search_cfg = _read_mapping(
            cal_cfg.get("search"),
            "wafer_particles.calibrate_search.search",
        )
        bins_cfg = _read_mapping(
            cal_cfg.get("bins"),
            "wafer_particles.calibrate_search.bins",
        )
        score_cfg = _read_mapping(
            cal_cfg.get("score"),
            "wafer_particles.calibrate_search.score",
            required=False,
        )
        spatial_cfg = _read_mapping(
            cal_cfg.get("spatial"),
            "wafer_particles.calibrate_search.spatial",
            required=False,
        )

        allow_repo_paths = _real_data_allow_repo_paths(cfg)
        real_input = _load_real_input(
            real_cfg,
            repo_root=writer.repo_root,
            writer=writer,
            allow_repo_paths=allow_repo_paths,
        )
        validate_particles_table(real_input.particles)
        validate_samples_table(real_input.samples)
        _ensure_comparable(cfg, real_input)

        r_edges = _resolve_edges(bins_cfg.get("r"), "calibrate_search.bins.r")
        theta_edges = _resolve_edges(bins_cfg.get("theta"), "calibrate_search.bins.theta")
        size_edges = _resolve_edges(bins_cfg.get("size"), "calibrate_search.bins.size")

        seed = _coerce_int(cfg.get("seed"), "seed")
        nn_max_points = _coerce_optional_positive_int(
            spatial_cfg.get("nn_max_points"),
            "calibrate_search.spatial.nn_max_points",
        )
        weights = _resolve_weights(score_cfg)
        enable_nn = _resolve_enable_nn(spatial_cfg, weights)

        real_metrics = _compute_reference_metrics(
            real_input.particles,
            r_edges=r_edges,
            theta_edges=theta_edges,
            size_edges=size_edges,
            nn_max_points=nn_max_points,
            enable_nn=enable_nn,
            seed=seed,
        )

        base_wp_cfg = _strip_calibrate_cfg(wp_cfg)
        param_specs = _resolve_param_specs(search_cfg.get("params"), base_wp_cfg)
        warm_start = _resolve_warm_start(search_cfg.get("warm_start"))
        include_baseline = _coerce_bool(search_cfg.get("include_baseline"), default=True)
        n_trials = _coerce_positive_int(search_cfg.get("n_trials"), "search.n_trials")
        seed_offset = _coerce_int(search_cfg.get("seed_offset", 0), "search.seed_offset")
        algorithm = str(search_cfg.get("algorithm", "random"))
        if algorithm.lower() not in {"random"}:
            raise ValueError(f"unsupported search.algorithm: {algorithm}")

        search_rng = random.Random(_derive_seed(seed, seed_offset, "calibrate_search"))
        trial_results: list[TrialResult] = []
        best_result: TrialResult | None = None
        trial_index = 0

        def _evaluate(params: dict[str, Any], trial_type: str) -> None:
            nonlocal trial_index, best_result
            trial_seed = _derive_seed(seed, seed_offset + trial_index, "calibrate_trial")
            candidate_cfg = _apply_param_overrides(base_wp_cfg, params, param_specs)
            particles, samples = _generate_tables(candidate_cfg, seed=trial_seed)
            metrics = _compute_distance_metrics(
                particles,
                real_metrics=real_metrics,
                r_edges=r_edges,
                theta_edges=theta_edges,
                size_edges=size_edges,
                nn_max_points=nn_max_points,
                enable_nn=enable_nn,
                seed=trial_seed,
            )
            score = _score_metrics(metrics, weights)
            result = TrialResult(
                trial=trial_index,
                trial_type=trial_type,
                seed=trial_seed,
                params=params,
                score=score,
                metrics=metrics,
                n_particles=len(particles),
                n_samples=len(samples),
            )
            trial_results.append(result)
            if best_result is None or score < best_result.score:
                best_result = result
            trial_index += 1

        if include_baseline:
            _evaluate({}, "baseline")

        for entry in warm_start:
            _evaluate(entry, "warm_start")

        for _ in range(n_trials):
            params = _sample_params(param_specs, search_rng)
            _evaluate(params, "random")

        if best_result is None:
            raise RuntimeError("calibrate_search produced no trials")

        _write_trials_csv(writer.run_dir / "metrics" / "trials.csv", trial_results, param_specs)

        best_payload = _build_best_payload(
            cfg=cfg,
            real_input=real_input,
            bins_cfg=bins_cfg,
            weights=weights,
            search_cfg=search_cfg,
            include_baseline=include_baseline,
            warm_start=warm_start,
            best_result=best_result,
            trial_results=trial_results,
        )
        writer.write_json("metrics/best_score.json", best_payload)

        best_cfg = _best_generator_config(cfg, base_wp_cfg, best_result.params, param_specs)
        _write_yaml(writer.run_dir / "config" / "best_config.yaml", best_cfg)
        writer.log("calibrate_search complete")


def _resolve_wafer_particles_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    return dict(wp_cfg)


def _strip_calibrate_cfg(wp_cfg: Mapping[str, Any]) -> dict[str, Any]:
    base = _deepcopy_mapping(wp_cfg)
    base.pop("calibrate_search", None)
    return base


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _deepcopy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(value))


def _resolve_weights(score_cfg: Mapping[str, Any]) -> dict[str, float]:
    weights_cfg = score_cfg.get("weights")
    if not isinstance(weights_cfg, Mapping):
        weights_cfg = {}
    defaults = {
        "hist_r_l1": 1.0,
        "hist_theta_l1": 1.0,
        "hist_size_l1": 1.0,
        "nn_distance_ks": 0.0,
    }
    resolved = dict(defaults)
    for key, value in weights_cfg.items():
        if key in resolved and value is not None:
            resolved[key] = float(value)
        elif key == "r_hist_l1" and value is not None:
            resolved["hist_r_l1"] = float(value)
        elif key == "theta_hist_l1" and value is not None:
            resolved["hist_theta_l1"] = float(value)
        elif key == "size_hist_l1" and value is not None:
            resolved["hist_size_l1"] = float(value)
    return resolved


def _resolve_enable_nn(spatial_cfg: Mapping[str, Any], weights: Mapping[str, float]) -> bool:
    enabled = spatial_cfg.get("enable_nn")
    if enabled is None:
        enabled = False
    enable_nn = _coerce_bool(enabled, default=False)
    if weights.get("nn_distance_ks", 0.0) > 0.0:
        enable_nn = True
    return enable_nn


def _load_real_input(
    real_cfg: Mapping[str, Any],
    *,
    repo_root: Path,
    writer,
    allow_repo_paths: bool,
) -> RealInput:
    run_dir = real_cfg.get("run_dir")
    manifest_path = real_cfg.get("manifest_path")
    run_name = real_cfg.get("run_name")
    samples_path = real_cfg.get("samples_path")
    if run_dir or manifest_path or run_name or samples_path:
        paths = resolve_input_paths(
            real_cfg,
            repo_root=repo_root,
            default_process_name="wafer_particles.process.generate",
        )
        _enforce_real_data_paths(_real_input_paths(paths), repo_root, allow_repo_paths, writer)
        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        return RealInput(
            particles=particles,
            samples=samples,
            input_payload=_sanitize_payload(input_payload(paths), repo_root),
            input_config=paths.input_config,
            samples_generated=False,
        )

    particles_path = real_cfg.get("particles_path")
    if not particles_path:
        raise ValueError("calibrate_search real input requires particles_path or run_dir/manifest_path")
    resolved_particles = resolve_path(particles_path, repo_root)
    resolved_samples = resolve_path(samples_path, repo_root) if samples_path else None
    _enforce_real_data_paths(
        [path for path in [resolved_particles, resolved_samples] if path is not None],
        repo_root,
        allow_repo_paths,
        writer,
    )
    if not resolved_particles.exists():
        raise ValueError("real particles file not found")
    particles = read_table(resolved_particles)
    if resolved_samples and resolved_samples.exists():
        samples = read_table(resolved_samples)
        samples_generated = False
    else:
        samples, warnings = _samples_from_particles(particles)
        for warning in warnings:
            writer.log(warning)
        samples_generated = True
    payload = {
        "run_dir": None,
        "manifest_path": None,
        "particles_path": str(resolved_particles),
        "samples_path": str(resolved_samples) if resolved_samples else None,
        "samples_generated": samples_generated,
    }
    return RealInput(
        particles=particles,
        samples=samples,
        input_payload=_sanitize_payload(payload, repo_root),
        input_config=None,
        samples_generated=samples_generated,
    )


def _samples_from_particles(
    particles: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    grouped: dict[str, dict[str, int]] = {}
    counts: dict[str, int] = {}
    for particle in particles:
        sample_id = str(particle.get("sample_id"))
        label = str(particle.get("label"))
        grouped.setdefault(sample_id, {}).setdefault(label, 0)
        grouped[sample_id][label] += 1
        counts[sample_id] = counts.get(sample_id, 0) + 1

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for sample_id in sorted(counts.keys()):
        label_counts = grouped.get(sample_id, {})
        if not label_counts:
            label = ""
        else:
            label = max(label_counts.items(), key=lambda item: item[1])[0]
        if len(label_counts) > 1:
            warnings.append(
                f"calibrate_search sample_id={sample_id} has mixed labels {sorted(label_counts.keys())}"
            )
        rows.append(
            {
                "sample_id": sample_id,
                "label": label,
                "n_particles": counts[sample_id],
                "pattern_params": "{}",
                "seed_offset": 0,
            }
        )
    return rows, warnings


def _resolve_param_specs(params_cfg: Any, base_wp_cfg: Mapping[str, Any]) -> list[ParamSpec]:
    specs: list[ParamSpec] = []
    if params_cfg is None:
        return specs
    if isinstance(params_cfg, Mapping):
        items = []
        for name, entry in params_cfg.items():
            if not isinstance(entry, Mapping):
                raise ValueError("search.params entries must be mappings")
            entry = dict(entry)
            entry.setdefault("name", str(name))
            entry.setdefault("path", str(entry.get("path") or name))
            items.append(entry)
        params_cfg = items
    if not isinstance(params_cfg, list):
        raise ValueError("search.params must be a list or mapping")
    for entry in params_cfg:
        if not isinstance(entry, Mapping):
            raise ValueError("search.params entries must be mappings")
        name = str(entry.get("name") or entry.get("path") or "")
        path = str(entry.get("path") or "")
        if not name or not path:
            raise ValueError("search.params entries require name and path")
        base_value = _get_by_path(base_wp_cfg, path)
        if base_value is _MISSING:
            raise ValueError(f"search.params path not found in base config: {path}")
        min_value = entry.get("min", entry.get("low", entry.get("start")))
        max_value = entry.get("max", entry.get("high", entry.get("stop")))
        values = entry.get("values")
        dtype = entry.get("type")
        if dtype is not None:
            dtype = str(dtype).lower()
        if values is not None:
            if not isinstance(values, list) or not values:
                raise ValueError(f"search.params[{name}].values must be a non-empty list")
        else:
            if min_value is None or max_value is None:
                raise ValueError(f"search.params[{name}] requires min/max or values")
            min_value = float(min_value)
            max_value = float(max_value)
            if min_value > max_value:
                raise ValueError(f"search.params[{name}] min must be <= max")
        specs.append(
            ParamSpec(
                name=name,
                path=path,
                min_value=float(min_value) if min_value is not None else None,
                max_value=float(max_value) if max_value is not None else None,
                values=list(values) if values is not None else None,
                dtype=dtype,
                base_value=base_value,
            )
        )
    return specs


def _resolve_warm_start(warm_cfg: Any) -> list[dict[str, Any]]:
    if warm_cfg is None:
        return []
    if isinstance(warm_cfg, Mapping):
        return [dict(warm_cfg)]
    if isinstance(warm_cfg, list):
        entries: list[dict[str, Any]] = []
        for entry in warm_cfg:
            if not isinstance(entry, Mapping):
                raise ValueError("warm_start entries must be mappings")
            entries.append(dict(entry))
        return entries
    raise ValueError("warm_start must be a mapping or list of mappings")


def _sample_params(specs: Sequence[ParamSpec], rng: random.Random) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for spec in specs:
        if spec.values is not None:
            choice = rng.choice(spec.values)
            params[spec.path] = _coerce_param_value(choice, spec)
            continue
        min_value = float(spec.min_value)
        max_value = float(spec.max_value)
        sampled = rng.uniform(min_value, max_value) if min_value != max_value else min_value
        params[spec.path] = _coerce_param_value(sampled, spec)
    return params


def _coerce_param_value(value: Any, spec: ParamSpec) -> Any:
    dtype = spec.dtype
    if dtype == "int":
        return int(round(float(value)))
    if dtype == "float":
        return float(value)
    if isinstance(spec.base_value, int) and not isinstance(spec.base_value, bool):
        return int(round(float(value)))
    if isinstance(spec.base_value, float):
        return float(value)
    return value


def _apply_param_overrides(
    base_wp_cfg: Mapping[str, Any],
    params: Mapping[str, Any],
    specs: Sequence[ParamSpec],
) -> dict[str, Any]:
    resolved = _deepcopy_mapping(base_wp_cfg)
    if not params:
        return resolved
    allowed = {spec.path: spec for spec in specs} if specs else None
    for path, value in params.items():
        if allowed is not None and path not in allowed:
            raise ValueError(f"unknown parameter path in warm_start: {path}")
        _set_by_path(resolved, path, value)
    return resolved


def _set_by_path(cfg: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cursor: Any = cfg
    for part in parts[:-1]:
        if not isinstance(cursor, Mapping) or part not in cursor:
            raise ValueError(f"missing config path: {path}")
        cursor = cursor[part]
    if not isinstance(cursor, Mapping):
        raise ValueError(f"invalid config path: {path}")
    cursor[parts[-1]] = value


def _get_by_path(cfg: Mapping[str, Any], path: str) -> Any:
    parts = path.split(".")
    cursor: Any = cfg
    for part in parts:
        if not isinstance(cursor, Mapping) or part not in cursor:
            return _MISSING
        cursor = cursor[part]
    return cursor


def _compute_reference_metrics(
    particles: list[dict[str, Any]],
    *,
    r_edges: list[float],
    theta_edges: list[float],
    size_edges: list[float],
    nn_max_points: int | None,
    enable_nn: bool,
    seed: int,
) -> dict[str, Any]:
    r_values = _extract_values(particles, "r_mm")
    theta_values = _extract_values(particles, "theta_rad")
    size_values = _extract_values(particles, "size_um")

    hist_r, _ = _compute_hist(r_values, r_edges)
    hist_theta, _ = _compute_hist(theta_values, theta_edges)
    hist_size, _ = _compute_hist(size_values, size_edges)
    nn_distances = None
    if enable_nn:
        rng = random.Random(_derive_seed(seed, 0, "real_nn"))
        points = _collect_sample_points(particles, max_points=nn_max_points, rng=rng)
        nn_distances = _nearest_neighbor_distances(points)
    return {
        "hist_r": hist_r,
        "hist_theta": hist_theta,
        "hist_size": hist_size,
        "nn_distances": nn_distances,
    }


def _compute_distance_metrics(
    particles: list[dict[str, Any]],
    *,
    real_metrics: Mapping[str, Any],
    r_edges: list[float],
    theta_edges: list[float],
    size_edges: list[float],
    nn_max_points: int | None,
    enable_nn: bool,
    seed: int,
) -> dict[str, Any]:
    r_values = _extract_values(particles, "r_mm")
    theta_values = _extract_values(particles, "theta_rad")
    size_values = _extract_values(particles, "size_um")

    hist_r, _ = _compute_hist(r_values, r_edges)
    hist_theta, _ = _compute_hist(theta_values, theta_edges)
    hist_size, _ = _compute_hist(size_values, size_edges)

    r_l1 = _hist_l1(real_metrics["hist_r"], hist_r)
    theta_l1 = _hist_l1(real_metrics["hist_theta"], hist_theta)
    size_l1 = _hist_l1(real_metrics["hist_size"], hist_size)

    nn_ks = None
    if enable_nn:
        rng = random.Random(_derive_seed(seed, 0, "trial_nn"))
        points = _collect_sample_points(particles, max_points=nn_max_points, rng=rng)
        nn_distances = _nearest_neighbor_distances(points)
        nn_ks = _ks_statistic(real_metrics.get("nn_distances") or [], nn_distances)

    return {
        "hist_r_l1": r_l1,
        "hist_theta_l1": theta_l1,
        "hist_size_l1": size_l1,
        "nn_distance_ks": nn_ks,
    }


def _score_metrics(metrics: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    score = 0.0
    for key, weight in weights.items():
        if weight == 0.0:
            continue
        value = metrics.get(key)
        if value is None:
            raise ValueError(f"missing metric for score: {key}")
        score += float(weight) * float(value)
    return score


def _extract_values(particles: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for particle in particles:
        value = particle.get(key)
        if value is None:
            continue
        values.append(float(value))
    return values


def _hist_l1(values_a: list[int], values_b: list[int]) -> float:
    if len(values_a) != len(values_b):
        raise ValueError("hist lengths must match")
    total_a = sum(values_a)
    total_b = sum(values_b)
    if total_a == 0 and total_b == 0:
        return 0.0
    if total_a == 0 or total_b == 0:
        return 1.0
    norm_a = [value / total_a for value in values_a]
    norm_b = [value / total_b for value in values_b]
    return sum(abs(a - b) for a, b in zip(norm_a, norm_b))


def _collect_sample_points(
    particles: Sequence[Mapping[str, Any]],
    *,
    max_points: int | None,
    rng: random.Random,
) -> Mapping[str, list[tuple[float, float]]]:
    grouped: dict[str, list[tuple[int, float, float]]] = {}
    for particle in particles:
        sample_id = particle.get("sample_id")
        if sample_id is None:
            continue
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        x_mm = particle.get("x_mm")
        y_mm = particle.get("y_mm")
        if x_mm is None or y_mm is None:
            x_mm, y_mm = polar_to_cartesian_mm(r_mm, theta_rad)
        particle_id = int(particle.get("particle_id", 0))
        grouped.setdefault(str(sample_id), []).append((particle_id, float(x_mm), float(y_mm)))

    sampled: dict[str, list[tuple[float, float]]] = {}
    for sample_id in sorted(grouped.keys()):
        points = sorted(grouped[sample_id], key=lambda row: row[0])
        coords = [(x, y) for _, x, y in points]
        if max_points is not None and max_points > 0 and len(coords) > max_points:
            indices = sorted(rng.sample(range(len(coords)), max_points))
            coords = [coords[idx] for idx in indices]
        sampled[sample_id] = coords
    return sampled


def _ks_statistic(values_a: list[float], values_b: list[float]) -> float:
    if not values_a and not values_b:
        return 0.0
    if not values_a or not values_b:
        return 1.0
    a = sorted(values_a)
    b = sorted(values_b)
    n = len(a)
    m = len(b)
    i = 0
    j = 0
    max_diff = 0.0
    while i < n or j < m:
        if j >= m:
            value = a[i]
        elif i >= n:
            value = b[j]
        else:
            value = a[i] if a[i] <= b[j] else b[j]
        while i < n and a[i] == value:
            i += 1
        while j < m and b[j] == value:
            j += 1
        diff = abs((i / n) - (j / m))
        if diff > max_diff:
            max_diff = diff
    return max_diff


def _generate_tables(
    wp_cfg: Mapping[str, Any],
    *,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    n_samples = _coerce_positive_int(wp_cfg.get("n_samples"), "wafer_particles.n_samples")
    label_selection = _read_mapping(wp_cfg.get("label_selection"), "wafer_particles.label_selection")
    pattern_catalog = load_pattern_catalog(wp_cfg)
    patterns_cfg = pattern_catalog.enabled_configs()
    label_defs = _resolve_label_defs(wp_cfg.get("labels"), patterns_cfg)
    label_rng = random.Random(_derive_seed(seed, 0, "label_selection"))
    labels = _select_labels(n_samples, label_selection, label_defs, label_rng)

    sample_id_prefix = str(wp_cfg.get("sample_id_prefix", "sample"))
    include_xy = bool(wp_cfg.get("include_xy", True))
    source = wp_cfg.get("source")
    sample_ctx = _build_sample_ctx(wp_cfg)
    global_n_particles_dist = wp_cfg.get("n_particles_distribution")
    size_model_cfg = _resolve_size_model_cfg(wp_cfg)
    noise_cfg = _read_mapping(wp_cfg.get("noise"), "wafer_particles.noise", required=False)
    jitter_cfg = _read_mapping(noise_cfg.get("jitter"), "wafer_particles.noise.jitter", required=False)
    background_cfg = _read_mapping(
        noise_cfg.get("background"),
        "wafer_particles.noise.background",
        required=False,
    )
    jitter_enabled, jitter_r_std, jitter_theta_std = _resolve_jitter_cfg(jitter_cfg)
    background_enabled, background_count, background_fraction = _resolve_background_cfg(background_cfg)

    particles: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for idx, label in enumerate(labels):
        sample_particles, sample_row, _ = _generate_sample(
            idx=idx,
            label=label,
            seed=seed,
            sample_id_prefix=sample_id_prefix,
            label_defs=label_defs,
            sample_ctx=sample_ctx,
            global_n_particles_dist=global_n_particles_dist,
            size_model_cfg=size_model_cfg,
            include_xy=include_xy,
            source=source,
            jitter_enabled=jitter_enabled,
            jitter_r_std=jitter_r_std,
            jitter_theta_std=jitter_theta_std,
            background_enabled=background_enabled,
            background_count=background_count,
            background_fraction=background_fraction,
        )
        particles.extend(sample_particles)
        samples.append(sample_row)
    validate_particles_table(particles)
    validate_samples_table(samples)
    return particles, samples


def _resolve_patterns_cfg(wp_cfg: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    catalog = load_pattern_catalog(wp_cfg)
    return catalog.enabled_configs()


def _resolve_label_defs(
    labels_cfg: Any,
    patterns_cfg: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    label_defs: dict[str, dict[str, Any]] = {}
    if isinstance(labels_cfg, Mapping) and "labels" in labels_cfg:
        entries = labels_cfg.get("labels")
        if not isinstance(entries, list):
            raise ValueError("wafer_particles.labels.labels must be a list")
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError("label entry must be a mapping")
            base_name = entry.get("name")
            if not base_name:
                raise ValueError("label name is required")
            base_name = str(base_name)
            base_cfg = patterns_cfg.get(base_name)
            if base_cfg is None:
                continue
            label_defs[base_name] = _deepcopy_mapping(base_cfg)
            variants = entry.get("variants") or []
            if variants:
                if not isinstance(variants, list):
                    raise ValueError("label variants must be a list")
                for variant in variants:
                    if not isinstance(variant, Mapping):
                        raise ValueError("label variant must be a mapping")
                    variant_name = variant.get("name")
                    if not variant_name:
                        raise ValueError("variant name is required")
                    params = variant.get("params") or {}
                    if not isinstance(params, Mapping):
                        raise ValueError("variant params must be a mapping")
                    merged_cfg = _deepcopy_mapping(base_cfg)
                    merged_cfg.update(params)
                    label_defs[str(variant_name)] = merged_cfg
        for label, cfg in patterns_cfg.items():
            if label not in label_defs:
                label_defs[str(label)] = _deepcopy_mapping(cfg)
    else:
        for label, cfg in patterns_cfg.items():
            label_defs[str(label)] = _deepcopy_mapping(cfg)

    for label, cfg in label_defs.items():
        if not cfg.get("name"):
            raise ValueError(f"pattern name is required for label {label}")
    if not label_defs:
        raise ValueError("no labels available for generation")
    return label_defs


def _select_labels(
    n_samples: int,
    selection_cfg: Mapping[str, Any],
    label_defs: Mapping[str, Mapping[str, Any]],
    rng: random.Random,
) -> list[str]:
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    mode = str(selection_cfg.get("mode", "ratio")).lower()
    available = list(label_defs.keys())

    def _validate(chosen: list[str]) -> list[str]:
        missing = sorted({label for label in chosen if label not in label_defs})
        if missing:
            raise ValueError(f"unknown labels in selection: {missing}")
        return chosen

    if mode == "fixed":
        labels = selection_cfg.get("labels")
        if not isinstance(labels, list) or not labels:
            raise ValueError("label_selection.labels must be a non-empty list for fixed mode")
        chosen = [str(label) for label in labels]
        if len(chosen) >= n_samples:
            return _validate(chosen[:n_samples])
        out: list[str] = []
        idx = 0
        while len(out) < n_samples:
            out.append(chosen[idx % len(chosen)])
            idx += 1
        return _validate(out)

    if mode == "random":
        labels = selection_cfg.get("labels")
        pool = [str(label) for label in labels] if isinstance(labels, list) and labels else available
        if not pool:
            raise ValueError("label_selection.labels must be non-empty for random mode")
        return _validate([rng.choice(pool) for _ in range(n_samples)])

    if mode != "ratio":
        raise ValueError(f"unsupported label_selection.mode: {mode}")

    ratios = selection_cfg.get("ratios")
    if ratios is None:
        ratios = {}
    if not isinstance(ratios, Mapping):
        raise ValueError("label_selection.ratios must be a mapping")
    ratios = {str(label): float(weight) for label, weight in ratios.items() if str(label) in label_defs}
    if not ratios:
        labels = selection_cfg.get("labels")
        labels = [str(label) for label in labels] if isinstance(labels, list) and labels else available
        labels = [label for label in labels if label in label_defs]
        if not labels:
            labels = available
        ratios = {label: 1.0 for label in labels}

    labels = [str(label) for label in ratios.keys()]
    weights = [float(ratios[label]) for label in labels]
    counts = _allocate_counts(n_samples, weights)
    chosen: list[str] = []
    for label, count in zip(labels, counts):
        chosen.extend([label] * count)
    if selection_cfg.get("shuffle", True):
        rng.shuffle(chosen)
    return _validate(chosen)


def _allocate_counts(total: int, weights: Sequence[float]) -> list[int]:
    if total <= 0:
        return [0 for _ in weights]
    if not weights:
        return []
    if any(weight < 0 for weight in weights):
        raise ValueError("label_selection.ratios must be non-negative")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("label_selection.ratios must sum to > 0")
    raw = [total * weight / total_weight for weight in weights]
    counts = [int(value) for value in raw]
    remainder = total - sum(counts)
    if remainder <= 0:
        return counts
    fractions = [value - int(value) for value in raw]
    order = sorted(range(len(fractions)), key=lambda idx: (-fractions[idx], idx))
    for idx in range(remainder):
        counts[order[idx]] += 1
    return counts


def _build_sample_ctx(wp_cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    sample_ctx: dict[str, Any] = {}
    n_particles = wp_cfg.get("n_particles")
    if n_particles is not None:
        sample_ctx["n_particles"] = int(n_particles)
    wafer_radius_mm = wp_cfg.get("wafer_radius_mm")
    if wafer_radius_mm is not None:
        sample_ctx["wafer_radius_mm"] = float(wafer_radius_mm)
    return sample_ctx or None


def _resolve_size_model_cfg(wp_cfg: Mapping[str, Any]) -> dict[str, Any]:
    size_cfg = wp_cfg.get("size_models") or wp_cfg.get("size_model")
    if not isinstance(size_cfg, Mapping):
        raise ValueError("wafer_particles.size_models config is required")
    return _deepcopy_mapping(size_cfg)


def _resolve_jitter_cfg(cfg: Mapping[str, Any]) -> tuple[bool, float, float]:
    enabled = bool(cfg.get("enabled", False))
    r_std = cfg.get("r_std_mm", 0.0)
    theta_std = cfg.get("theta_std_rad", 0.0)
    try:
        r_std = float(r_std)
        theta_std = float(theta_std)
    except (TypeError, ValueError):
        raise ValueError("wafer_particles.noise.jitter std must be numeric")
    if r_std < 0 or theta_std < 0:
        raise ValueError("wafer_particles.noise.jitter std must be non-negative")
    return enabled and (r_std > 0.0 or theta_std > 0.0), r_std, theta_std


def _resolve_background_cfg(cfg: Mapping[str, Any]) -> tuple[bool, int | None, float | None]:
    enabled = bool(cfg.get("enabled", False))
    count = cfg.get("count")
    fraction = cfg.get("fraction")
    if count is not None:
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise ValueError("wafer_particles.noise.background.count must be an int")
        if count < 0:
            raise ValueError("wafer_particles.noise.background.count must be non-negative")
    if fraction is not None:
        try:
            fraction = float(fraction)
        except (TypeError, ValueError):
            raise ValueError("wafer_particles.noise.background.fraction must be a float")
        if fraction < 0:
            raise ValueError("wafer_particles.noise.background.fraction must be non-negative")
    return enabled, count, fraction


def _derive_seed(base_seed: int, offset: int, component: str) -> int:
    payload = f"{base_seed}:{offset}:{component}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(base_seed) + int(digest[:12], 16)


def _generate_sample(
    *,
    idx: int,
    label: str,
    seed: int,
    sample_id_prefix: str,
    label_defs: Mapping[str, Mapping[str, Any]],
    sample_ctx: Mapping[str, Any] | None,
    global_n_particles_dist: Any,
    size_model_cfg: Mapping[str, Any],
    include_xy: bool,
    source: Any,
    jitter_enabled: bool,
    jitter_r_std: float,
    jitter_theta_std: float,
    background_enabled: bool,
    background_count: int | None,
    background_fraction: float | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    seed_offset = idx
    sample_id = f"{sample_id_prefix}_{idx:06d}"
    pattern_cfg = _deepcopy_mapping(label_defs[label])
    param_rng = np.random.default_rng(_derive_seed(seed, seed_offset, "pattern_params"))
    count_rng = random.Random(_derive_seed(seed, seed_offset, "n_particles"))
    pattern_rng = random.Random(_derive_seed(seed, seed_offset, "pattern"))
    size_rng = random.Random(_derive_seed(seed, seed_offset, "size_model"))
    _apply_param_space(pattern_cfg, param_rng, path=f"wafer_particles.patterns.{label}")
    n_particles = _resolve_n_particles(pattern_cfg, global_n_particles_dist, count_rng)
    resolved_sample_ctx = _resolve_sample_ctx(sample_ctx, n_particles)
    if n_particles is not None:
        pattern_cfg["n_particles"] = n_particles
        pattern_cfg.pop("mean_particles", None)
    _inject_sample_ctx_defaults(pattern_cfg, resolved_sample_ctx)
    pattern_name = str(pattern_cfg.get("name", ""))
    ctx = resolve_sample_ctx(pattern_cfg, resolved_sample_ctx)
    generator = get_pattern(pattern_name)
    sample_particles = _invoke_pattern(generator, ctx, pattern_cfg, pattern_rng)

    if jitter_enabled:
        jitter_rng = random.Random(_derive_seed(seed, seed_offset, "jitter"))
        apply_position_jitter(
            sample_particles,
            jitter_rng,
            r_std_mm=jitter_r_std,
            theta_std_rad=jitter_theta_std,
            wafer_radius_mm=ctx.wafer_radius_mm,
        )

    if background_enabled:
        base_count = len(sample_particles)
        extra_count = resolve_background_count(
            base_count,
            count=background_count,
            fraction=background_fraction,
        )
        if extra_count > 0:
            background_rng = random.Random(_derive_seed(seed, seed_offset, "background"))
            sample_particles.extend(
                generate_background_particles(
                    background_rng,
                    extra_count,
                    wafer_radius_mm=ctx.wafer_radius_mm,
                )
            )

    _finalize_particles(sample_particles, ctx)

    for particle_id, particle in enumerate(sample_particles):
        particle["sample_id"] = sample_id
        particle["particle_id"] = particle_id
        particle["label_fine"] = label
        particle["label"] = label
        if source is not None:
            particle["source"] = str(source)
    apply_size_model(size_model_cfg, size_rng, sample_particles)
    if include_xy:
        _append_cartesian(sample_particles)

    n_particles = len(sample_particles)
    sample_row = {
        "sample_id": sample_id,
        "label": label,
        "n_particles": n_particles,
        "pattern_params": json.dumps(pattern_cfg, sort_keys=True, ensure_ascii=True),
        "seed_offset": seed_offset,
    }
    return sample_particles, sample_row, n_particles


def _invoke_pattern(
    generator: Any,
    ctx: PatternContext,
    params: Mapping[str, Any],
    rng: random.Random,
) -> list[dict[str, Any]]:
    if hasattr(generator, "generate"):
        return generator.generate(ctx, params, rng)
    warnings.warn(
        f"pattern {generator} uses legacy callable interface; update to PatternBase",
        RuntimeWarning,
        stacklevel=3,
    )
    sample_ctx = {"n_particles": ctx.n_particles, "wafer_radius_mm": ctx.wafer_radius_mm}
    return generator(params, rng, sample_ctx)


def _finalize_particles(particles: list[dict[str, Any]], ctx: PatternContext) -> None:
    if not particles:
        return
    for particle in particles:
        if "theta_rad" not in particle:
            raise ValueError("particle missing theta_rad")
        theta_rad = float(particle["theta_rad"]) % math.tau
        particle["theta_rad"] = theta_rad

        if particle.get("r_norm") is None:
            if particle.get("r_mm") is None:
                raise ValueError("particle missing r_norm/r_mm")
            warnings.warn(
                "particle missing r_norm; mapping from r_mm",
                RuntimeWarning,
                stacklevel=3,
            )
            r_norm = float(particle["r_mm"]) / ctx.wafer_radius_mm
        else:
            r_norm = float(particle["r_norm"])

        if r_norm < -1e-6 or r_norm > 1.0 + 1e-6:
            raise ValueError("particle r_norm out of bounds")
        if r_norm < 0.0 or r_norm > 1.0:
            r_norm = min(max(r_norm, 0.0), 1.0)

        particle["r_norm"] = r_norm
        particle["r_mm"] = norm_to_mm(r_norm, ctx.wafer_radius_mm)

        if "component" in particle and "component_label_fine" not in particle:
            warnings.warn(
                "particle component is deprecated; use component_label_fine",
                RuntimeWarning,
                stacklevel=3,
            )
            particle["component_label_fine"] = str(particle["component"])
        if "component_label_fine" in particle and "component" not in particle:
            particle["component"] = str(particle["component_label_fine"])


def _append_cartesian(particles: list[dict[str, Any]]) -> None:
    for particle in particles:
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        x_mm, y_mm = polar_to_cartesian_mm(r_mm, theta_rad)
        particle["x_mm"] = x_mm
        particle["y_mm"] = y_mm


def _apply_param_space(pattern_cfg: dict[str, Any], rng: np.random.Generator, *, path: str) -> None:
    param_space.apply_param_space(pattern_cfg, rng, path=path)
    return float(value)


def _range_bounds(cfg: Mapping[str, Any], name: str) -> tuple[float, float]:
    min_value = cfg.get("min", cfg.get("low", cfg.get("start")))
    max_value = cfg.get("max", cfg.get("high", cfg.get("stop")))
    if min_value is None or max_value is None:
        raise ValueError(f"{name} range requires min/max")
    min_value = float(min_value)
    max_value = float(max_value)
    if min_value > max_value:
        raise ValueError(f"{name} range must satisfy min<=max")
    return min_value, max_value


def _resolve_n_particles(
    pattern_cfg: dict[str, Any],
    global_dist: Any,
    rng: random.Random,
) -> int | None:
    dist_cfg: Any = None
    if "n_particles_distribution" in pattern_cfg:
        dist_cfg = pattern_cfg.pop("n_particles_distribution")
    elif global_dist is not None:
        dist_cfg = global_dist
    if dist_cfg is None:
        return None
    return _sample_n_particles(dist_cfg, rng)


def _sample_n_particles(dist_cfg: Any, rng: random.Random) -> int:
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
            elif _has_keys(cfg, ("value", "count")):
                dist_type = "fixed"
        if dist_type in {"fixed", "value"} or not dist_type:
            value = cfg.get("value", cfg.get("count", cfg.get("n_particles")))
            return _coerce_positive_int(value, "n_particles_distribution.value")
        if dist_type in {"range", "uniform"}:
            min_value, max_value = _range_bounds(cfg, "n_particles_distribution")
            return _sample_int_range(min_value, max_value, rng, "n_particles_distribution")
        if dist_type == "poisson":
            mean = cfg.get("mean", cfg.get("mu", cfg.get("lambda")))
            return _sample_poisson_positive(mean, rng, "n_particles_distribution.mean")
        if dist_type in {"negative_binomial", "neg_binomial", "nb"}:
            return _sample_negative_binomial_from_cfg(cfg, rng)
        raise ValueError(f"unsupported n_particles_distribution type: {dist_type}")
    if isinstance(dist_cfg, (list, tuple)):
        if len(dist_cfg) != 2:
            raise ValueError("n_particles_distribution range must have 2 values")
        min_value = float(dist_cfg[0])
        max_value = float(dist_cfg[1])
        if min_value > max_value:
            raise ValueError("n_particles_distribution range must satisfy min<=max")
        return _sample_int_range(min_value, max_value, rng, "n_particles_distribution")
    return _coerce_positive_int(dist_cfg, "n_particles_distribution")


def _has_range_keys(cfg: Mapping[str, Any]) -> bool:
    return any(key in cfg for key in ("min", "max", "low", "high", "start", "stop"))


def _has_keys(cfg: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(key in cfg and cfg.get(key) is not None for key in keys)


def _sample_int_range(min_value: float, max_value: float, rng: random.Random, name: str) -> int:
    if max_value < 1:
        raise ValueError(f"{name} range must allow positive integers")
    min_int = int(math.ceil(min_value))
    max_int = int(math.floor(max_value))
    if min_int <= 0:
        min_int = 1
    if min_int > max_int:
        raise ValueError(f"{name} range must satisfy min<=max after integer coercion")
    if min_int == max_int:
        return min_int
    return int(rng.randint(min_int, max_int))


def _sample_poisson_positive(mean: Any, rng: random.Random, name: str) -> int:
    if mean is None:
        raise ValueError(f"{name} is required")
    mean = float(mean)
    if mean <= 0:
        raise ValueError(f"{name} must be positive")
    for _ in range(10):
        count = sample_poisson(rng, mean)
        if count > 0:
            return count
    return 1


def _sample_negative_binomial_from_cfg(cfg: Mapping[str, Any], rng: random.Random) -> int:
    mean = cfg.get("mean")
    dispersion = cfg.get("dispersion", cfg.get("r", cfg.get("k")))
    if mean is None or dispersion is None:
        if cfg.get("n") is not None and cfg.get("p") is not None:
            dispersion = float(cfg["n"])
            p_value = float(cfg["p"])
            if dispersion <= 0 or p_value <= 0 or p_value >= 1:
                raise ValueError("n_particles_distribution.n must be positive and p must be in (0,1)")
            mean = dispersion * (1.0 - p_value) / p_value
        else:
            raise ValueError("negative_binomial requires mean+dispersion or n+p")
    mean = float(mean)
    dispersion = float(dispersion)
    if mean <= 0 or dispersion <= 0:
        raise ValueError("negative_binomial mean/dispersion must be positive")
    for _ in range(10):
        count = _sample_negative_binomial(rng, mean, dispersion)
        if count > 0:
            return count
    return 1


def _sample_negative_binomial(rng: random.Random, mean: float, dispersion: float) -> int:
    if mean <= 0:
        return 0
    scale = mean / dispersion
    lambda_value = rng.gammavariate(dispersion, scale)
    return sample_poisson(rng, lambda_value)


def _resolve_sample_ctx(sample_ctx: Mapping[str, Any] | None, n_particles: int | None) -> dict[str, Any] | None:
    if sample_ctx is None and n_particles is None:
        return None
    resolved = dict(sample_ctx) if sample_ctx else {}
    if n_particles is not None:
        resolved["n_particles"] = int(n_particles)
    return resolved


def _inject_sample_ctx_defaults(pattern_cfg: dict[str, Any], sample_ctx: Mapping[str, Any] | None) -> None:
    if not sample_ctx:
        return
    for key in ("n_particles", "wafer_radius_mm"):
        if key in sample_ctx and pattern_cfg.get(key) is None:
            pattern_cfg[key] = sample_ctx[key]


def _write_trials_csv(
    path: Path,
    trials: Sequence[TrialResult],
    specs: Sequence[ParamSpec],
) -> None:
    fieldnames = [
        "trial",
        "trial_type",
        "seed",
        "score",
        "hist_r_l1",
        "hist_theta_l1",
        "hist_size_l1",
        "nn_distance_ks",
        "n_particles",
        "n_samples",
    ]
    for spec in specs:
        fieldnames.append(spec.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in trials:
            row = {
                "trial": result.trial,
                "trial_type": result.trial_type,
                "seed": result.seed,
                "score": result.score,
                "hist_r_l1": result.metrics.get("hist_r_l1"),
                "hist_theta_l1": result.metrics.get("hist_theta_l1"),
                "hist_size_l1": result.metrics.get("hist_size_l1"),
                "nn_distance_ks": result.metrics.get("nn_distance_ks"),
                "n_particles": result.n_particles,
                "n_samples": result.n_samples,
            }
            for spec in specs:
                row[spec.name] = result.params.get(spec.path)
            writer.writerow(row)


def _build_best_payload(
    *,
    cfg: Mapping[str, Any],
    real_input: RealInput,
    bins_cfg: Mapping[str, Any],
    weights: Mapping[str, float],
    search_cfg: Mapping[str, Any],
    include_baseline: bool,
    warm_start: Sequence[Mapping[str, Any]],
    best_result: TrialResult,
    trial_results: Sequence[TrialResult],
) -> dict[str, Any]:
    baseline = None
    for result in trial_results:
        if result.trial_type == "baseline":
            baseline = {
                "trial": result.trial,
                "score": result.score,
                "metrics": dict(result.metrics),
            }
            break
    return {
        "schema_version": str(cfg.get("schema_version", SCHEMA_VERSION)),
        "domain": _domain_name(cfg),
        "input": {
            "real": dict(real_input.input_payload),
        },
        "bins": dict(bins_cfg),
        "weights": dict(weights),
        "search": {
            "algorithm": str(search_cfg.get("algorithm", "random")),
            "n_trials": int(search_cfg.get("n_trials", 0)),
            "seed_offset": int(search_cfg.get("seed_offset", 0)),
            "include_baseline": bool(include_baseline),
            "warm_start_count": len(warm_start),
        },
        "baseline": baseline,
        "best": {
            "trial": best_result.trial,
            "score": best_result.score,
            "metrics": dict(best_result.metrics),
            "params": dict(best_result.params),
        },
    }


def _best_generator_config(
    cfg: Mapping[str, Any],
    base_wp_cfg: Mapping[str, Any],
    best_params: Mapping[str, Any],
    specs: Sequence[ParamSpec],
) -> dict[str, Any]:
    resolved = _apply_param_overrides(base_wp_cfg, best_params, specs)
    return {
        "schema_version": str(cfg.get("schema_version", SCHEMA_VERSION)),
        "domain": cfg.get("domain") or {"name": DOMAIN_NAME},
        "wafer_particles": resolved,
    }


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(payload, sort_keys=True, allow_unicode=False)
    path.write_text(text, encoding="utf-8")


def _coerce_positive_int(value: Any, name: str) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an int")
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _coerce_int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an int")


def _coerce_optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    parsed = _coerce_int(value, name)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
    return bool(value)


def _ensure_comparable(cfg: Mapping[str, Any], real_input: RealInput) -> None:
    input_cfg = real_input.input_config
    if not input_cfg:
        return
    expected_schema = str(cfg.get("schema_version", SCHEMA_VERSION))
    expected_domain = _domain_name(cfg)
    schema = input_cfg.get("schema_version")
    if schema and str(schema) != expected_schema:
        raise ValueError(f"schema_version mismatch for real input: {schema}")
    domain = _domain_name(input_cfg)
    if domain and domain != expected_domain:
        raise ValueError(f"domain mismatch for real input: {domain}")


def _real_data_allow_repo_paths(cfg: Mapping[str, Any]) -> bool:
    policy_cfg = cfg.get("policy")
    if isinstance(policy_cfg, Mapping):
        real_cfg = policy_cfg.get("real_data")
        if isinstance(real_cfg, Mapping):
            return _coerce_bool(real_cfg.get("allow_repo_paths"), default=False)
    return False


def _real_input_paths(paths: InputPaths) -> list[Path]:
    items: list[Path] = []
    if paths.run_dir:
        items.append(paths.run_dir)
    if paths.manifest_path:
        items.append(paths.manifest_path)
    items.append(paths.particles_path)
    items.append(paths.samples_path)
    return items


def _enforce_real_data_paths(
    paths: list[Path],
    repo_root: Path,
    allow_repo_paths: bool,
    writer,
) -> None:
    repo_root_resolved = repo_root.resolve()
    in_repo = any(_is_within_repo(path, repo_root_resolved) for path in paths)
    if not in_repo:
        return
    if allow_repo_paths:
        writer.log("real_data input resolved under repo root; policy allows but this is discouraged")
        return
    raise ValueError(
        "real_data inputs must live outside repository root "
        "(set policy.real_data.allow_repo_paths=true to override)"
    )


def _is_within_repo(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root)
        return True
    except Exception:
        return False


def _sanitize_payload(payload: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    sanitized = dict(payload)
    for key in ["run_dir", "manifest_path", "particles_path", "samples_path"]:
        if key in sanitized:
            sanitized[key] = _sanitize_path(sanitized.get(key), repo_root)
    return sanitized


def _sanitize_path(value: Any, repo_root: Path) -> str | None:
    if not value:
        return None
    path = Path(str(value))
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        return str(rel)
    except Exception:
        return path.name


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
