from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    build_manifest,
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
from synthlab.domains.wafer_particles.generators.size_models.common import (
    apply_size_model,
    resolve_size_model_name,
)
from synthlab.domains.wafer_particles.metrics.size_stats import (
    DEFAULT_QUANTILES,
    compute_size_stats_by_label,
    compute_size_stats_from_particles,
)
from synthlab.domains.wafer_particles.noise import (
    apply_position_jitter,
    generate_background_particles,
    resolve_background_count,
)
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import get_pattern, register_process

import synthlab.domains.wafer_particles.generators  # noqa: F401

_SAMPLE_ANOMALY_RESERVED_COLUMNS = {
    "sample_id",
    "label",
    "size_model",
    "size_params_json",
    "label_coarse",
    "label_family",
    "labels_fine",
    "label_fine_primary",
    "components_json",
    "n_particles",
    "pattern_params",
    "seed_offset",
    "size_anomaly_type",
}


@register_process("wafer_particles.process.generate")
class GenerateProcess(BaseProcess):
    name = "wafer_particles.process.generate"

    def run(self, writer) -> None:
        writer.log("generate start")
        cfg = self.cfg
        wp_cfg = _resolve_wafer_particles_cfg(cfg)
        seed = int(cfg.get("seed"))
        n_samples = _coerce_positive_int(wp_cfg.get("n_samples"), "wafer_particles.n_samples")
        label_selection = _read_mapping(wp_cfg.get("label_selection"), "wafer_particles.label_selection")
        pattern_catalog = load_pattern_catalog(wp_cfg, warn=writer.log)
        patterns_cfg = pattern_catalog.enabled_configs()
        labels_cfg = wp_cfg.get("labels")
        label_defs = _resolve_label_defs(labels_cfg, patterns_cfg)
        label_meta = _resolve_label_meta(labels_cfg)

        label_rng = random.Random(_derive_seed(seed, 0, "label_selection"))
        labels = _select_labels(n_samples, label_selection, label_defs, label_rng)

        sample_id_prefix = str(wp_cfg.get("sample_id_prefix", "sample"))
        include_xy = bool(wp_cfg.get("include_xy", True))
        source = wp_cfg.get("source")
        sample_ctx = _build_sample_ctx(wp_cfg)
        global_n_particles_dist = wp_cfg.get("n_particles_distribution")
        size_model_cfg = _resolve_size_model_cfg(wp_cfg)
        size_model_selection = _prepare_size_model_selection(size_model_cfg, n_samples, seed)
        size_anomaly_label_name = None
        if size_model_selection is not None:
            anomaly_cfg = size_model_selection.get("anomaly")
            if anomaly_cfg:
                label_name = anomaly_cfg.get("label_name")
                if label_name:
                    size_anomaly_label_name = str(label_name)
        size_model_per_sample = bool(size_model_cfg.get("per_sample", False))
        record_size_model = _should_record_size_model(size_model_cfg, size_model_selection)
        if size_model_selection is None and not size_model_per_sample:
            size_param_rng = np.random.default_rng(_derive_seed(seed, 0, "size_model_params"))
            _apply_param_space(size_model_cfg, size_param_rng, path="wafer_particles.size_models")
        noise_cfg = _read_mapping(wp_cfg.get("noise"), "wafer_particles.noise", required=False)
        jitter_cfg = _read_mapping(noise_cfg.get("jitter"), "wafer_particles.noise.jitter", required=False)
        background_cfg = _read_mapping(
            noise_cfg.get("background"),
            "wafer_particles.noise.background",
            required=False,
        )
        jitter_enabled, jitter_r_std, jitter_theta_std = _resolve_jitter_cfg(jitter_cfg)
        background_enabled, background_count, background_fraction = _resolve_background_cfg(background_cfg)

        io_cfg = _read_mapping(wp_cfg.get("io"), "wafer_particles.io")
        fmt_raw = str(io_cfg.get("format", "auto")).lower()
        fmt, auto_selected = _resolve_output_format(fmt_raw)
        if auto_selected:
            writer.log(f"io.format=auto resolved to {fmt}")
        write_mode = _resolve_write_mode(io_cfg.get("write_mode"))
        generate_cfg = _read_mapping(wp_cfg.get("generate"), "wafer_particles.generate", required=False)
        chunk_size = _resolve_chunk_size(generate_cfg.get("chunk_size"), n_samples)
        csv_cfg = _read_mapping(io_cfg.get("csv"), "wafer_particles.io.csv", required=False)
        parquet_cfg = _resolve_parquet_cfg(
            io_cfg,
            _read_mapping(io_cfg.get("parquet"), "wafer_particles.io.parquet", required=False),
        )

        label_distribution: dict[str, int] = {}
        particle_label_distribution: dict[str, int] = {}

        particles_path, samples_path = _data_paths(fmt)
        particles_rows = 0
        samples_rows = 0
        size_stats: dict[str, Any]
        size_stats_by_label: dict[str, Any]

        if write_mode == "streaming":
            writer.log(f"generate streaming enabled (chunk_size={chunk_size})")
            unique_labels = set(labels)
            include_components = _has_component_columns(label_defs, unique_labels)
            include_components_json = include_components
            include_label_coarse = _has_label_meta(label_meta, unique_labels, "coarse")
            include_label_family = _has_label_meta(label_meta, unique_labels, "family")
            particle_columns = _particle_columns_for_streaming(
                include_xy=include_xy,
                include_source=source is not None,
                include_components=include_components,
            )
            sample_columns = _sample_columns_for_streaming(
                include_label_coarse=include_label_coarse,
                include_label_family=include_label_family,
                include_components_json=include_components_json,
                include_size_model_info=record_size_model,
                size_anomaly_label_name=size_anomaly_label_name,
            )
            particles_writer = _StreamingTableWriter(
                writer.run_dir / particles_path,
                fmt=fmt,
                columns=particle_columns,
                csv_cfg=csv_cfg,
                parquet_cfg=parquet_cfg,
            )
            samples_writer = _StreamingTableWriter(
                writer.run_dir / samples_path,
                fmt=fmt,
                columns=sample_columns,
                csv_cfg=csv_cfg,
                parquet_cfg=parquet_cfg,
            )
            size_values: list[float] = []
            size_values_by_label: dict[str, list[float]] = {}
            try:
                for start in range(0, n_samples, chunk_size):
                    end = min(start + chunk_size, n_samples)
                    particles_chunk: list[dict[str, Any]] = []
                    samples_chunk: list[dict[str, Any]] = []
                    for idx in range(start, end):
                        label = labels[idx]
                        sample_particles, sample_row, n_particles = _generate_sample(
                            idx=idx,
                            label=label,
                            seed=seed,
                            sample_id_prefix=sample_id_prefix,
                            label_defs=label_defs,
                            sample_ctx=sample_ctx,
                            global_n_particles_dist=global_n_particles_dist,
                            size_model_cfg=size_model_cfg,
                            size_model_per_sample=size_model_per_sample,
                            size_model_selection=size_model_selection,
                            record_size_model=record_size_model,
                            include_xy=include_xy,
                            source=source,
                            jitter_enabled=jitter_enabled,
                            jitter_r_std=jitter_r_std,
                            jitter_theta_std=jitter_theta_std,
                            background_enabled=background_enabled,
                            background_count=background_count,
                            background_fraction=background_fraction,
                            label_meta=label_meta,
                        )
                        particles_chunk.extend(sample_particles)
                        samples_chunk.append(sample_row)
                        label_distribution[label] = label_distribution.get(label, 0) + 1
                        particle_label_distribution[label] = (
                            particle_label_distribution.get(label, 0) + n_particles
                        )
                        for particle in sample_particles:
                            size_value = float(particle["size_um"])
                            size_values.append(size_value)
                            size_values_by_label.setdefault(label, []).append(size_value)
                        particles_rows += n_particles
                        samples_rows += 1
                    validate_particles_table(particles_chunk)
                    validate_samples_table(samples_chunk)
                    particles_writer.write_rows(particles_chunk)
                    samples_writer.write_rows(samples_chunk)
            finally:
                particles_writer.close()
                samples_writer.close()
            size_stats = _compute_size_stats_from_values(size_values, DEFAULT_QUANTILES)
            size_stats_by_label = {
                label: _compute_size_stats_from_values(values, DEFAULT_QUANTILES)
                for label, values in size_values_by_label.items()
            }
        else:
            particles: list[dict[str, Any]] = []
            samples: list[dict[str, Any]] = []
            for idx, label in enumerate(labels):
                sample_particles, sample_row, n_particles = _generate_sample(
                    idx=idx,
                    label=label,
                    seed=seed,
                    sample_id_prefix=sample_id_prefix,
                    label_defs=label_defs,
                    sample_ctx=sample_ctx,
                    global_n_particles_dist=global_n_particles_dist,
                    size_model_cfg=size_model_cfg,
                    size_model_per_sample=size_model_per_sample,
                    size_model_selection=size_model_selection,
                    record_size_model=record_size_model,
                    include_xy=include_xy,
                    source=source,
                    jitter_enabled=jitter_enabled,
                    jitter_r_std=jitter_r_std,
                    jitter_theta_std=jitter_theta_std,
                    background_enabled=background_enabled,
                    background_count=background_count,
                    background_fraction=background_fraction,
                    label_meta=label_meta,
                )
                particles.extend(sample_particles)
                samples.append(sample_row)
                label_distribution[label] = label_distribution.get(label, 0) + 1
                particle_label_distribution[label] = particle_label_distribution.get(label, 0) + n_particles
            validate_particles_table(particles)
            validate_samples_table(samples)
            _write_table(
                writer.run_dir / particles_path,
                particles,
                fmt=fmt,
                csv_cfg=csv_cfg,
                parquet_cfg=parquet_cfg,
                columns=_particle_columns(particles, include_xy=include_xy, include_source=source is not None),
            )
            _write_table(
                writer.run_dir / samples_path,
                samples,
                fmt=fmt,
                csv_cfg=csv_cfg,
                parquet_cfg=parquet_cfg,
                columns=_sample_columns(samples, size_anomaly_label_name=size_anomaly_label_name),
            )
            particles_rows = len(particles)
            samples_rows = len(samples)
            size_stats = compute_size_stats_from_particles(particles)
            size_stats_by_label = compute_size_stats_by_label(particles)

        domain = _domain_name(cfg)
        schema_version = cfg.get("schema_version", SCHEMA_VERSION)
        manifest = build_manifest(
            particles_path=particles_path,
            samples_path=samples_path,
            particles_rows=particles_rows,
            samples_rows=samples_rows,
            label_distribution=label_distribution,
            schema_version=str(schema_version),
            domain=str(domain),
        )
        writer.write_json("manifest.json", manifest)

        metrics = {
            "n_samples": n_samples,
            "n_particles": particles_rows,
            "label_distribution": label_distribution,
            "particle_label_distribution": particle_label_distribution,
            "size_stats": size_stats,
            "size_stats_by_label": size_stats_by_label,
        }
        writer.write_json("metrics/generate_summary.json", metrics)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=generate\n",
            encoding="utf-8",
        )
        writer.log("generate complete")


def _resolve_wafer_particles_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    return dict(wp_cfg)


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
            label_defs[base_name] = deepcopy(dict(base_cfg))
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
                    merged_cfg = deepcopy(dict(base_cfg))
                    merged_cfg.update(params)
                    label_defs[str(variant_name)] = merged_cfg
        for label, cfg in patterns_cfg.items():
            if label not in label_defs:
                label_defs[str(label)] = deepcopy(dict(cfg))
    else:
        for label, cfg in patterns_cfg.items():
            label_defs[str(label)] = deepcopy(dict(cfg))

    for label, cfg in label_defs.items():
        if not cfg.get("name"):
            raise ValueError(f"pattern name is required for label {label}")
    if not label_defs:
        raise ValueError("no labels available for generation")
    return label_defs


def _resolve_label_meta(labels_cfg: Any) -> dict[str, dict[str, str]]:
    if not isinstance(labels_cfg, Mapping) or "labels" not in labels_cfg:
        return {}
    entries = labels_cfg.get("labels")
    if not isinstance(entries, list):
        return {}
    label_meta: dict[str, dict[str, str]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        base_name = entry.get("name")
        if not base_name:
            continue
        base_meta = _label_meta(entry)
        label_meta[str(base_name)] = dict(base_meta)
        variants = entry.get("variants") or []
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, Mapping):
                continue
            variant_name = variant.get("name")
            if not variant_name:
                continue
            label_meta[str(variant_name)] = _label_meta(variant, base_meta=base_meta)
    return label_meta


def _label_meta(entry: Mapping[str, Any], *, base_meta: Mapping[str, str] | None = None) -> dict[str, str]:
    meta: dict[str, str] = dict(base_meta) if base_meta else {}
    coarse = entry.get("coarse")
    if coarse is None:
        coarse = entry.get("category")
    if coarse is not None:
        meta["coarse"] = str(coarse)
    family = entry.get("family")
    if family is not None:
        meta["family"] = str(family)
    return meta


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


def _prepare_size_model_selection(
    size_model_cfg: Mapping[str, Any],
    n_samples: int,
    seed: int,
) -> dict[str, Any] | None:
    selection_cfg = size_model_cfg.get("selection")
    if selection_cfg is None:
        return None
    if not isinstance(selection_cfg, Mapping):
        raise ValueError("wafer_particles.size_models.selection must be a mapping")
    models_cfg = size_model_cfg.get("models")
    if not isinstance(models_cfg, Mapping) or not models_cfg:
        raise ValueError("wafer_particles.size_models.models must be a non-empty mapping")
    base_cfg = _strip_size_model_selection(size_model_cfg)
    resolved_models: dict[str, dict[str, Any]] = {}
    for model_name, model_cfg in models_cfg.items():
        if not isinstance(model_cfg, Mapping):
            raise ValueError(f"wafer_particles.size_models.models.{model_name} must be a mapping")
        merged = _merge_size_model_cfg(base_cfg, model_cfg)
        if not merged.get("type") and not merged.get("name"):
            merged["type"] = str(model_name)
        if not bool(merged.get("per_sample", False)):
            size_param_rng = np.random.default_rng(
                _derive_seed(seed, 0, f"size_model_params:{model_name}")
            )
            _apply_param_space(
                merged,
                size_param_rng,
                path=f"wafer_particles.size_models.models.{model_name}",
            )
        resolved_models[str(model_name)] = merged
    size_model_rng = random.Random(_derive_seed(seed, 0, "size_model_selection"))
    selected = _select_size_models(
        n_samples,
        selection_cfg,
        list(resolved_models.keys()),
        size_model_rng,
    )
    anomaly_cfg = _resolve_size_anomaly_cfg(selection_cfg, list(resolved_models.keys()))
    return {"names": selected, "models": resolved_models, "anomaly": anomaly_cfg}


def _resolve_size_anomaly_cfg(
    selection_cfg: Mapping[str, Any],
    model_names: Sequence[str],
) -> dict[str, Any] | None:
    anomaly_types = selection_cfg.get("anomaly_types")
    if anomaly_types is None:
        return None
    if not isinstance(anomaly_types, list):
        raise ValueError("size_models.selection.anomaly_types must be a list")
    if not anomaly_types:
        return None
    resolved: list[str] = []
    for name in anomaly_types:
        resolved.append(_resolve_model_key(str(name), model_names))
    label_name = selection_cfg.get("anomaly_label_name", "is_size_anomaly")
    if label_name is None:
        label_name = "is_size_anomaly"
    label_name = str(label_name).strip()
    if not label_name:
        raise ValueError("size_models.selection.anomaly_label_name must be a non-empty string")
    _validate_anomaly_label_name(label_name)
    return {
        "label_name": label_name,
        "types": list(dict.fromkeys(resolved)),
    }


def _validate_anomaly_label_name(label_name: str) -> None:
    if label_name in _SAMPLE_ANOMALY_RESERVED_COLUMNS:
        raise ValueError(
            "size_models.selection.anomaly_label_name conflicts with existing samples columns"
        )


def _select_size_models(
    n_samples: int,
    selection_cfg: Mapping[str, Any],
    model_names: Sequence[str],
    rng: random.Random,
) -> list[str]:
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    if not model_names:
        raise ValueError("size_models.models must have at least one entry")
    mode = str(selection_cfg.get("mode", "ratio")).lower()
    resolved = [_resolve_model_key(name, model_names) for name in model_names]
    model_names = list(dict.fromkeys(resolved))

    def _shuffle_if(chosen: list[str], *, default: bool) -> list[str]:
        if selection_cfg.get("shuffle", default):
            rng.shuffle(chosen)
        return chosen

    if mode == "single":
        model = selection_cfg.get("model", selection_cfg.get("type", selection_cfg.get("name")))
        if model is None:
            raise ValueError("size_models.selection.model is required for single mode")
        resolved_name = _resolve_model_key(str(model), model_names)
        return _shuffle_if([resolved_name] * n_samples, default=False)

    if mode == "list":
        models = selection_cfg.get("models", selection_cfg.get("list"))
        if not isinstance(models, list) or not models:
            raise ValueError("size_models.selection.models must be a non-empty list for list mode")
        resolved_list = [_resolve_model_key(str(model), model_names) for model in models]
        if len(resolved_list) >= n_samples:
            return _shuffle_if(resolved_list[:n_samples], default=False)
        out: list[str] = []
        idx = 0
        while len(out) < n_samples:
            out.append(resolved_list[idx % len(resolved_list)])
            idx += 1
        return _shuffle_if(out, default=False)

    if mode != "ratio":
        raise ValueError(f"unsupported size_models.selection.mode: {mode}")

    ratios = selection_cfg.get("ratios") or {}
    if not isinstance(ratios, Mapping):
        raise ValueError("size_models.selection.ratios must be a mapping")
    weights: dict[str, float] = {}
    for name, weight in ratios.items():
        resolved_name = _resolve_model_key(str(name), model_names)
        weights[resolved_name] = weights.get(resolved_name, 0.0) + float(weight)
    if not weights:
        weights = {name: 1.0 for name in model_names}

    labels = list(weights.keys())
    counts = _allocate_counts(n_samples, [weights[label] for label in labels])
    chosen: list[str] = []
    for label, count in zip(labels, counts):
        chosen.extend([label] * count)
    return _shuffle_if(chosen, default=True)


def _resolve_model_key(name: str, model_names: Sequence[str]) -> str:
    if name in model_names:
        return name
    short = _format_size_model_name(name)
    for model_name in model_names:
        if _format_size_model_name(model_name) == short:
            return model_name
    raise ValueError(f"unknown size model in selection: {name}")


def _strip_size_model_selection(cfg: Mapping[str, Any]) -> dict[str, Any]:
    cleaned = dict(cfg)
    cleaned.pop("selection", None)
    cleaned.pop("models", None)
    return cleaned


def _merge_size_model_cfg(base_cfg: Mapping[str, Any], model_cfg: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base_cfg)
    merged.update(deepcopy(model_cfg))
    return merged


def _format_size_model_name(name: str) -> str:
    prefix = "wafer_particles.size_model."
    return name[len(prefix):] if name.startswith(prefix) else name


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


def _derive_seed(base_seed: int, offset: int, component: str) -> int:
    payload = f"{base_seed}:{offset}:{component}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(base_seed) + int(digest[:12], 16)


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


def _build_sample_ctx(wp_cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    sample_ctx: dict[str, Any] = {}
    n_particles = wp_cfg.get("n_particles")
    if n_particles is not None:
        sample_ctx["n_particles"] = int(n_particles)
    wafer_radius_mm = wp_cfg.get("wafer_radius_mm")
    if wafer_radius_mm is not None:
        sample_ctx["wafer_radius_mm"] = float(wafer_radius_mm)
    return sample_ctx or None


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


def _append_cartesian(particles: list[dict[str, Any]]) -> None:
    for particle in particles:
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        x_mm, y_mm = polar_to_cartesian_mm(r_mm, theta_rad)
        particle["x_mm"] = x_mm
        particle["y_mm"] = y_mm


def _resolve_size_model_cfg(wp_cfg: Mapping[str, Any]) -> dict[str, Any]:
    size_cfg = wp_cfg.get("size_models") or wp_cfg.get("size_model")
    if not isinstance(size_cfg, Mapping):
        raise ValueError("wafer_particles.size_models config is required")
    return deepcopy(dict(size_cfg))


def _should_record_size_model(
    size_model_cfg: Mapping[str, Any],
    size_model_selection: Mapping[str, Any] | None,
) -> bool:
    return True


def _resolve_size_model_cfg_for_label(
    cfg: Mapping[str, Any],
    label: str | None,
) -> dict[str, Any]:
    merged = deepcopy(dict(cfg))
    by_label = merged.pop("by_label", None)
    if label is None or by_label is None:
        return merged
    if not isinstance(by_label, Mapping):
        raise ValueError("size model by_label must be a mapping")
    label_cfg = by_label.get(label)
    if label_cfg is None:
        return merged
    if not isinstance(label_cfg, Mapping):
        raise ValueError("label size model config must be a mapping")
    merged.update(deepcopy(dict(label_cfg)))
    merged.pop("by_label", None)
    return merged


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _build_size_model_params(resolved_cfg: Mapping[str, Any], model_name: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "min_um": _optional_float(resolved_cfg.get("min_um")),
        "max_um": _optional_float(resolved_cfg.get("max_um")),
        "per_sample": bool(resolved_cfg.get("per_sample", False)),
    }
    if model_name == "gaussian":
        params["mean_um"] = _optional_float(resolved_cfg.get("mean_um"))
        params["std_um"] = _optional_float(resolved_cfg.get("std_um"))
    elif model_name == "lognormal":
        params["mu_log"] = _optional_float(resolved_cfg.get("mu_log"))
        params["sigma_log"] = _optional_float(resolved_cfg.get("sigma_log"))
    elif model_name == "weibull":
        params["k"] = _optional_float(resolved_cfg.get("k"))
        params["lambda_um"] = _optional_float(resolved_cfg.get("lambda_um"))
    elif model_name == "pareto":
        params["alpha"] = _optional_float(resolved_cfg.get("alpha"))
        params["xm_um"] = _optional_float(resolved_cfg.get("xm_um"))
    elif model_name == "mixture":
        params["components"] = _build_mixture_component_params(resolved_cfg)
    return params


def _build_mixture_component_params(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    components = cfg.get("components")
    if not isinstance(components, list) or not components:
        return []
    resolved: list[dict[str, Any]] = []
    for idx, component in enumerate(components):
        if not isinstance(component, Mapping):
            raise ValueError(f"component {idx} must be a mapping")
        name = component.get("name")
        if not name:
            name = f"component_{idx}"
        weight = component.get("weight", 1.0)
        try:
            weight_value = float(weight)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"component {idx} weight must be numeric") from exc
        model_cfg = _resolve_component_model_cfg(component, idx)
        model_name = _format_size_model_name(resolve_size_model_name(model_cfg))
        resolved.append(
            {
                "name": str(name),
                "weight": weight_value,
                "model_type": model_name,
                "params": _build_size_model_params(model_cfg, model_name),
            }
        )
    return resolved


def _resolve_component_model_cfg(component: Mapping[str, Any], idx: int) -> dict[str, Any]:
    model_entry = component.get("model")
    if isinstance(model_entry, Mapping):
        model_cfg = deepcopy(dict(model_entry))
    else:
        cfg_entry = component.get("cfg") or {}
        if not isinstance(cfg_entry, Mapping):
            raise ValueError(f"component {idx} cfg must be a mapping")
        model_cfg = deepcopy(dict(cfg_entry))
        if model_entry is not None:
            if not isinstance(model_entry, str):
                raise ValueError(f"component {idx} model must be a mapping or string")
            if not model_cfg.get("type") and not model_cfg.get("name"):
                model_cfg["type"] = model_entry

    model_name = model_cfg.get("type") or model_cfg.get("name")
    if not model_name:
        component_type = component.get("type")
        if component_type:
            model_name = component_type
    if not model_name:
        raise ValueError(f"component {idx} requires model")
    model_cfg.setdefault("type", model_name)
    model_cfg.pop("by_label", None)
    return model_cfg


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _resolve_write_mode(value: Any) -> str:
    if value is None:
        return "eager"
    mode = str(value).lower()
    if mode not in {"eager", "streaming"}:
        raise ValueError(f"unsupported io.write_mode: {mode}")
    return mode


def _resolve_chunk_size(value: Any, n_samples: int, *, default: int = 1000) -> int:
    if value is None:
        chunk = default
    else:
        try:
            chunk = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("wafer_particles.generate.chunk_size must be an int") from exc
    if chunk <= 0:
        raise ValueError("wafer_particles.generate.chunk_size must be positive")
    if n_samples <= 0:
        return chunk
    return min(chunk, n_samples)


def _resolve_parquet_cfg(io_cfg: Mapping[str, Any], parquet_cfg: Mapping[str, Any]) -> dict[str, Any]:
    resolved = dict(parquet_cfg) if parquet_cfg else {}
    compression = io_cfg.get("compression")
    if compression is not None:
        resolved["compression"] = compression
    return resolved


def _apply_param_space(pattern_cfg: dict[str, Any], rng: np.random.Generator, *, path: str) -> None:
    param_space.apply_param_space(pattern_cfg, rng, path=path)


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
    size_model_per_sample: bool,
    size_model_selection: Mapping[str, Any] | None,
    record_size_model: bool,
    include_xy: bool,
    source: Any,
    jitter_enabled: bool,
    jitter_r_std: float,
    jitter_theta_std: float,
    background_enabled: bool,
    background_count: int | None,
    background_fraction: float | None,
    label_meta: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    seed_offset = idx
    sample_id = f"{sample_id_prefix}_{idx:06d}"
    pattern_cfg = deepcopy(label_defs[label])
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
    size_model_key = None
    if size_model_selection is not None:
        size_model_key = str(size_model_selection["names"][seed_offset])
        model_cfg = size_model_selection["models"].get(size_model_key)
        if model_cfg is None:
            raise ValueError(f"unknown size model selection: {size_model_key}")
        resolved_size_model_cfg = model_cfg
        if bool(resolved_size_model_cfg.get("per_sample", False)):
            size_param_rng = np.random.default_rng(
                _derive_seed(seed, seed_offset, f"size_model_params:{size_model_key}")
            )
            resolved_size_model_cfg = deepcopy(resolved_size_model_cfg)
            _apply_param_space(
                resolved_size_model_cfg,
                size_param_rng,
                path=f"wafer_particles.size_models.models.{size_model_key}",
            )
    else:
        if size_model_per_sample:
            size_param_rng = np.random.default_rng(_derive_seed(seed, seed_offset, "size_model_params"))
            resolved_size_model_cfg = deepcopy(size_model_cfg)
            _apply_param_space(resolved_size_model_cfg, size_param_rng, path="wafer_particles.size_models")
        else:
            resolved_size_model_cfg = size_model_cfg
    label_size_model_cfg = _resolve_size_model_cfg_for_label(resolved_size_model_cfg, label)
    size_model_name = _format_size_model_name(resolve_size_model_name(label_size_model_cfg))
    apply_size_model(resolved_size_model_cfg, size_rng, sample_particles)
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
    anomaly_label_name = None
    anomaly_types: set[str] = set()
    if size_model_selection is not None:
        anomaly_cfg = size_model_selection.get("anomaly")
        if anomaly_cfg:
            anomaly_label_name = str(anomaly_cfg.get("label_name", "")).strip() or None
            anomaly_types = {str(name) for name in anomaly_cfg.get("types", [])}
    if anomaly_label_name is not None and size_model_key is not None:
        is_anomaly = int(size_model_key in anomaly_types)
        sample_row[anomaly_label_name] = is_anomaly
        anomaly_type = _format_size_model_name(size_model_key)
        sample_row["size_anomaly_type"] = anomaly_type if is_anomaly else "none"
    components_json = _components_json(pattern_cfg)
    if components_json is not None:
        sample_row["components_json"] = components_json
    meta = label_meta.get(label, {})
    label_coarse = meta.get("coarse")
    if label_coarse is not None:
        sample_row["label_coarse"] = label_coarse
    label_family = meta.get("family")
    if label_family is not None:
        sample_row["label_family"] = label_family
    if record_size_model:
        sample_row["size_model"] = size_model_name
        size_params = _build_size_model_params(label_size_model_cfg, size_model_name)
        sample_row["size_params_json"] = json.dumps(
            size_params,
            sort_keys=True,
            ensure_ascii=False,
        )
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


def _has_component_columns(label_defs: Mapping[str, Mapping[str, Any]], labels: set[str]) -> bool:
    for label in labels:
        cfg = label_defs.get(label)
        if cfg is None:
            continue
        if cfg.get("name") == "wafer_particles.pattern.composite":
            return True
        components = cfg.get("components")
        if isinstance(components, list) and components:
            return True
    return False


def _has_label_meta(
    label_meta: Mapping[str, Mapping[str, str]],
    labels: set[str],
    key: str,
) -> bool:
    for label in labels:
        meta = label_meta.get(label)
        if meta and key in meta:
            return True
    return False


def _particle_columns_for_streaming(
    *,
    include_xy: bool,
    include_source: bool,
    include_components: bool,
) -> list[str]:
    columns = [
        "sample_id",
        "particle_id",
        "r_norm",
        "theta_rad",
        "r_mm",
        "size_um",
        "label_fine",
        "label",
    ]
    if include_xy:
        columns.extend(["x_mm", "y_mm"])
    if include_components:
        columns.extend(["component_label_fine", "component", "component_id"])
    if include_source:
        columns.append("source")
    return columns


def _sample_columns_for_streaming(
    *,
    include_label_coarse: bool,
    include_label_family: bool,
    include_components_json: bool,
    include_size_model_info: bool,
    size_anomaly_label_name: str | None,
) -> list[str]:
    columns = ["sample_id", "label"]
    if include_size_model_info:
        columns.extend(["size_model", "size_params_json"])
    if size_anomaly_label_name:
        columns.append(size_anomaly_label_name)
        columns.append("size_anomaly_type")
    if include_label_coarse:
        columns.append("label_coarse")
    if include_label_family:
        columns.append("label_family")
    if include_components_json:
        columns.append("components_json")
    columns.extend(["n_particles", "pattern_params", "seed_offset"])
    return columns


def _compute_size_stats_from_values(
    values: list[float],
    quantiles: Sequence[float] | None,
) -> dict[str, Any]:
    if quantiles is None:
        quantiles = DEFAULT_QUANTILES
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
    values.sort()
    quantile_map = {_format_quantile_key(q): _percentile(values, float(q)) for q in quantiles}
    return {
        "count": count,
        "mean": mean,
        "std": std,
        "min": values[0],
        "max": values[-1],
        "quantiles": quantile_map,
    }


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


def _particle_columns(
    particles: Sequence[Mapping[str, Any]],
    *,
    include_xy: bool,
    include_source: bool,
) -> list[str]:
    columns = [
        "sample_id",
        "particle_id",
        "r_norm",
        "theta_rad",
        "r_mm",
        "size_um",
        "label_fine",
        "label",
    ]
    if include_xy:
        columns.extend(["x_mm", "y_mm"])
    has_component_label = any("component_label_fine" in particle for particle in particles)
    has_component = any("component" in particle for particle in particles)
    has_component_id = any("component_id" in particle for particle in particles)
    if has_component_label:
        columns.append("component_label_fine")
    if has_component:
        columns.append("component")
    if has_component_id:
        columns.append("component_id")
    if include_source:
        columns.append("source")
    return columns


def _sample_columns(
    samples: Sequence[Mapping[str, Any]],
    *,
    size_anomaly_label_name: str | None,
) -> list[str]:
    columns = ["sample_id", "label"]
    if any("size_model" in sample for sample in samples):
        columns.append("size_model")
    if any("size_params_json" in sample for sample in samples):
        columns.append("size_params_json")
    if size_anomaly_label_name:
        columns.append(size_anomaly_label_name)
        columns.append("size_anomaly_type")
    if any("label_coarse" in sample for sample in samples):
        columns.append("label_coarse")
    if any("label_family" in sample for sample in samples):
        columns.append("label_family")
    if any("components_json" in sample for sample in samples):
        columns.append("components_json")
    columns.extend(["n_particles", "pattern_params", "seed_offset"])
    return columns


def _components_json(cfg: Mapping[str, Any]) -> str | None:
    components = cfg.get("components")
    if not isinstance(components, list) or not components:
        return None
    return json.dumps(components, sort_keys=True, ensure_ascii=True)


def _data_paths(fmt: str) -> tuple[str, str]:
    if fmt == "csv":
        return "data/particles.csv", "data/samples.csv"
    if fmt == "parquet":
        return "data/particles.parquet", "data/samples.parquet"
    raise ValueError(f"unsupported io.format: {fmt}")


def _resolve_output_format(fmt: str) -> tuple[str, bool]:
    if fmt != "auto":
        return fmt, False
    try:
        import pyarrow  # noqa: F401
    except Exception:
        return "csv", True
    return "parquet", True


class _StreamingTableWriter:
    def __init__(
        self,
        path: Path,
        *,
        fmt: str,
        columns: Sequence[str],
        csv_cfg: Mapping[str, Any],
        parquet_cfg: Mapping[str, Any],
    ) -> None:
        self.path = path
        self.fmt = fmt
        self.columns = list(columns)
        self.csv_cfg = dict(csv_cfg) if csv_cfg else {}
        self.parquet_cfg = dict(parquet_cfg) if parquet_cfg else {}
        self._csv_handle = None
        self._csv_writer: csv.DictWriter[str] | None = None
        self._parquet_writer = None

    def write_rows(self, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            return
        if self.fmt == "csv":
            self._write_csv(rows)
            return
        if self.fmt == "parquet":
            self._write_parquet(rows)
            return
        raise ValueError(f"unsupported io.format: {self.fmt}")

    def close(self) -> None:
        if self._csv_handle is not None:
            self._csv_handle.close()
            self._csv_handle = None
        if self._parquet_writer is not None:
            self._parquet_writer.close()
            self._parquet_writer = None

    def _write_csv(self, rows: Sequence[Mapping[str, Any]]) -> None:
        if self._csv_writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            delimiter = str(self.csv_cfg.get("delimiter", ","))
            quotechar = str(self.csv_cfg.get("quotechar", '"'))
            self._csv_handle = self.path.open("w", encoding="utf-8", newline="")
            self._csv_writer = csv.DictWriter(
                self._csv_handle,
                fieldnames=self.columns,
                extrasaction="ignore",
                delimiter=delimiter,
                quotechar=quotechar,
            )
            self._csv_writer.writeheader()
        for row in rows:
            self._csv_writer.writerow(row)

    def _write_parquet(self, rows: Sequence[Mapping[str, Any]]) -> None:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except Exception as exc:
            raise RuntimeError(
                "pyarrow is required for parquet output (set wafer_particles.io.format=csv to use CSV)."
            ) from exc
        data = {col: [row.get(col) for row in rows] for col in self.columns}
        table = pa.Table.from_pydict(data)
        if self._parquet_writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            compression = self.parquet_cfg.get("compression") if self.parquet_cfg else None
            self._parquet_writer = pq.ParquetWriter(
                self.path,
                table.schema,
                compression=compression,
            )
        self._parquet_writer.write_table(table)


def _write_table(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fmt: str,
    csv_cfg: Mapping[str, Any],
    parquet_cfg: Mapping[str, Any],
    columns: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        _write_csv(path, rows, columns, csv_cfg)
        return
    if fmt == "parquet":
        _write_parquet(path, rows, columns, parquet_cfg)
        return
    raise ValueError(f"unsupported io.format: {fmt}")


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    cfg: Mapping[str, Any],
) -> None:
    delimiter = str(cfg.get("delimiter", ","))
    quotechar = str(cfg.get("quotechar", '"'))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(columns),
            extrasaction="ignore",
            delimiter=delimiter,
            quotechar=quotechar,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    cfg: Mapping[str, Any],
) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception as exc:
        raise RuntimeError(
            "pyarrow is required for parquet output (set wafer_particles.io.format=csv to use CSV)."
        ) from exc
    data = {col: [row.get(col) for row in rows] for col in columns}
    table = pa.Table.from_pydict(data)
    compression = cfg.get("compression") if cfg else None
    pq.write_table(table, path, compression=compression)


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
