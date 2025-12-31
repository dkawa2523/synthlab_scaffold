from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

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
from synthlab.domains.wafer_particles.generators.patterns.common import norm_to_mm, resolve_sample_ctx
from synthlab.domains.wafer_particles.generators.size_models.common import apply_size_model
from synthlab.domains.wafer_particles.metrics.qc_metrics import _compute_hist, _read_mapping, _resolve_edges
from synthlab.domains.wafer_particles.metrics.size_stats import compute_size_stats
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
    qc_metrics: dict[str, Any] | None


@register_process("wafer_particles.process.pattern_coverage")
class PatternCoverageProcess(BaseProcess):
    name = "wafer_particles.process.pattern_coverage"

    def run(self, writer) -> None:
        writer.log("pattern_coverage start")
        cfg = self.cfg
        wp_cfg = _resolve_wafer_particles_cfg(cfg)
        coverage_cfg = _resolve_coverage_cfg(cfg)
        real_cfg = _read_mapping(coverage_cfg.get("real_input"), "coverage.real_input")
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

        seed = _coerce_int(cfg.get("seed"), "seed")
        r_edges, theta_edges, size_edges = _resolve_bins(
            coverage_cfg,
            wp_cfg,
            real_input.particles,
        )
        epsilon = _resolve_epsilon(coverage_cfg)
        weights = _resolve_weights(coverage_cfg)

        real_metrics = _compute_reference_metrics(
            real_input.particles,
            r_edges=r_edges,
            theta_edges=theta_edges,
            size_edges=size_edges,
        )

        pattern_catalog = load_pattern_catalog(wp_cfg, warn=writer.log)
        patterns_cfg = pattern_catalog.enabled_configs()
        label_defs = _resolve_label_defs(wp_cfg.get("labels"), patterns_cfg)
        pattern_labels = _resolve_pattern_set(coverage_cfg.get("pattern_set"), label_defs)

        search_budget = _coerce_positive_int(
            coverage_cfg.get("search_budget", 6),
            "coverage.search_budget",
        )
        top_k = _coerce_positive_int(
            coverage_cfg.get("top_k", min(3, search_budget)),
            "coverage.top_k",
        )
        candidate_samples = _coerce_positive_int(
            coverage_cfg.get("candidate_samples", 1),
            "coverage.candidate_samples",
        )
        max_particles = _coerce_optional_positive_int(
            coverage_cfg.get("max_particles"),
            "coverage.max_particles",
        )

        total_real_particles = len(real_input.particles)
        if total_real_particles <= 0:
            raise ValueError("real input has no particles")
        target_particles = total_real_particles
        if max_particles is not None:
            target_particles = min(target_particles, max_particles)
        target_particles = max(target_particles, 1)
        particle_counts = _allocate_counts(target_particles, [1.0] * candidate_samples)

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

        include_xy = bool(wp_cfg.get("include_xy", True))
        sample_id_prefix = str(wp_cfg.get("sample_id_prefix", "coverage"))
        wafer_radius_mm = _resolve_wafer_radius_mm(wp_cfg, real_input.particles)

        pattern_results: dict[str, Any] = {}
        best_overall: dict[str, Any] | None = None
        best_overall_particles: list[dict[str, Any]] | None = None
        best_overall_kind = "pattern"

        for pattern_idx, label in enumerate(sorted(pattern_labels)):
            base_cfg = label_defs[label]
            pattern_name = str(base_cfg.get("name", ""))
            if not pattern_name:
                raise ValueError(f"pattern name is required for label {label}")
            candidates: list[dict[str, Any]] = []
            for trial in range(search_budget):
                param_seed = _derive_seed(seed, trial, f"coverage:param:{label}")
                param_rng = param_space.numpy_rng_from_random(random.Random(param_seed))
                candidate_cfg = _sample_pattern_cfg(base_cfg, param_rng, label)
                candidate_seed = _derive_seed(seed, trial, f"coverage:candidate:{label}")
                particles, samples = _generate_candidate_tables(
                    label=label,
                    pattern_cfg=candidate_cfg,
                    seed=candidate_seed,
                    sample_id_prefix=sample_id_prefix,
                    particle_counts=particle_counts,
                    wafer_radius_mm=wafer_radius_mm,
                    size_model_cfg=size_model_cfg,
                    include_xy=include_xy,
                    jitter_enabled=jitter_enabled,
                    jitter_r_std=jitter_r_std,
                    jitter_theta_std=jitter_theta_std,
                    background_enabled=background_enabled,
                    background_count=background_count,
                    background_fraction=background_fraction,
                )
                metrics = _compute_distance_metrics(
                    particles,
                    real_metrics=real_metrics,
                    r_edges=r_edges,
                    theta_edges=theta_edges,
                    size_edges=size_edges,
                    epsilon=epsilon,
                )
                score = _score_metrics(metrics, weights)
                candidate = {
                    "label": label,
                    "pattern_id": pattern_name,
                    "trial": trial,
                    "seed": candidate_seed,
                    "params": _sanitize_params(candidate_cfg),
                    "metrics": metrics,
                    "score": score,
                    "n_particles": len(particles),
                    "n_samples": len(samples),
                }
                candidates.append(candidate)
                if best_overall is None or score < float(best_overall["score"]):
                    best_overall = candidate
                    best_overall_particles = particles
                    best_overall_kind = "pattern"
            candidates.sort(key=lambda item: (float(item["score"]), int(item["trial"])))
            pattern_results[label] = {
                "pattern_id": pattern_name,
                "candidates": candidates[: min(top_k, len(candidates))],
                "best": candidates[0],
            }

        composite_cfg = _read_mapping(coverage_cfg.get("composite"), "coverage.composite", required=False)
        allow_composite = _coerce_bool(coverage_cfg.get("allow_composite_search"), default=False)
        composite_k = _coerce_int(coverage_cfg.get("composite_k", 2), "coverage.composite_k")
        composite_top_k = _coerce_positive_int(
            composite_cfg.get("top_k", min(2, top_k)),
            "coverage.composite.top_k",
        )
        max_combinations = _coerce_positive_int(
            composite_cfg.get("max_combinations", 50),
            "coverage.composite.max_combinations",
        )

        composite_best: dict[str, Any] | None = None
        composite_best_particles: list[dict[str, Any]] | None = None

        if allow_composite:
            candidate_pool = {
                label: info["candidates"][: min(composite_top_k, len(info["candidates"]))]
                for label, info in pattern_results.items()
                if info["pattern_id"] != "wafer_particles.pattern.composite"
            }
            labels = sorted(candidate_pool.keys())
            combinations_checked = 0
            for labels_combo in _label_combinations(labels, composite_k):
                if combinations_checked >= max_combinations:
                    break
                candidate_lists = [candidate_pool[label] for label in labels_combo]
                for candidate_combo in _candidate_product(candidate_lists, max_combinations - combinations_checked):
                    composite_params = _build_composite_params(candidate_combo)
                    composite_seed = _derive_seed(seed, combinations_checked, "coverage:composite")
                    particles, samples = _generate_candidate_tables(
                        label="composite",
                        pattern_cfg=composite_params,
                        seed=composite_seed,
                        sample_id_prefix=sample_id_prefix,
                        particle_counts=particle_counts,
                        wafer_radius_mm=wafer_radius_mm,
                        size_model_cfg=size_model_cfg,
                        include_xy=include_xy,
                        jitter_enabled=jitter_enabled,
                        jitter_r_std=jitter_r_std,
                        jitter_theta_std=jitter_theta_std,
                        background_enabled=background_enabled,
                        background_count=background_count,
                        background_fraction=background_fraction,
                    )
                    metrics = _compute_distance_metrics(
                        particles,
                        real_metrics=real_metrics,
                        r_edges=r_edges,
                        theta_edges=theta_edges,
                        size_edges=size_edges,
                        epsilon=epsilon,
                    )
                    score = _score_metrics(metrics, weights)
                    composite_candidate = {
                        "label": "composite",
                        "pattern_id": "wafer_particles.pattern.composite",
                        "trial": combinations_checked,
                        "seed": composite_seed,
                        "params": _sanitize_params(composite_params),
                        "metrics": metrics,
                        "score": score,
                        "n_particles": len(particles),
                        "n_samples": len(samples),
                        "components": [
                            {
                                "label": candidate["label"],
                                "pattern_id": candidate["pattern_id"],
                                "params": candidate["params"],
                                "score": candidate["score"],
                            }
                            for candidate in candidate_combo
                        ],
                    }
                    if composite_best is None or score < float(composite_best["score"]):
                        composite_best = composite_candidate
                        composite_best_particles = particles
                    combinations_checked += 1
                    if combinations_checked >= max_combinations:
                        break

        threshold = float(coverage_cfg.get("threshold_new_pattern", 0.3))
        best_choice = best_overall
        best_kind = best_overall_kind
        if composite_best is not None and best_overall is not None:
            if float(composite_best["score"]) < float(best_overall["score"]):
                best_choice = composite_best
                best_kind = "composite"
                best_overall_particles = composite_best_particles
        if best_choice is None:
            raise RuntimeError("pattern_coverage produced no candidates")

        decision = _decision_payload(best_choice, best_kind, threshold)

        top_patterns = [
            {
                "label": label,
                "pattern_id": info["pattern_id"],
                "score": info["best"]["score"],
                "metrics": info["best"]["metrics"],
                "params": info["best"]["params"],
            }
            for label, info in pattern_results.items()
        ]
        top_patterns.sort(key=lambda item: float(item["score"]))

        summary = {
            "schema_version": str(cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(cfg),
            "input": {
                "real": real_input.input_payload,
                "samples_generated": real_input.samples_generated,
                "qc_metrics_path": _qc_metrics_path(real_input.qc_metrics, writer.repo_root),
            },
            "bins": {
                "r_edges": r_edges,
                "theta_edges": theta_edges,
                "size_edges": size_edges,
            },
            "weights": weights,
            "search": {
                "search_budget": search_budget,
                "top_k": top_k,
                "pattern_set": list(pattern_labels),
            },
            "real_summary": {
                "n_particles": len(real_input.particles),
                "n_samples": len(real_input.samples),
            },
            "results": {
                "top_patterns": top_patterns,
                "patterns": pattern_results,
                "best": best_choice,
                "best_kind": best_kind,
                "composite_best": composite_best,
            },
            "decision": decision,
        }

        writer.write_json("reports/coverage_summary.json", summary)
        writer.write_json("metrics/coverage_summary.json", summary)
        _write_markdown(
            writer.run_dir / "reports" / "coverage_summary.md",
            summary,
        )
        _write_plots(
            writer,
            real_input.particles,
            best_overall_particles,
            r_edges,
            theta_edges,
            size_edges,
        )
        writer.log("pattern_coverage complete")


def _resolve_coverage_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    coverage_cfg = cfg.get("coverage")
    if isinstance(coverage_cfg, Mapping):
        return dict(coverage_cfg)
    wp_cfg = cfg.get("wafer_particles")
    if isinstance(wp_cfg, Mapping) and isinstance(wp_cfg.get("coverage"), Mapping):
        return dict(wp_cfg["coverage"])
    raise ValueError("coverage config is required")


def _resolve_wafer_particles_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    return dict(wp_cfg)


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
    qc_metrics_path = real_cfg.get("qc_metrics_path")

    qc_metrics = None
    if qc_metrics_path:
        path = resolve_path(qc_metrics_path, repo_root)
        _enforce_real_data_paths([path], repo_root, allow_repo_paths, writer)
        if not path.exists():
            raise ValueError("real qc_metrics file not found")
        qc_metrics = json.loads(path.read_text(encoding="utf-8"))

    if run_dir or manifest_path or run_name or samples_path:
        paths = resolve_input_paths(
            real_cfg,
            repo_root=repo_root,
            default_process_name="wafer_particles.process.generate",
        )
        _enforce_real_data_paths(_real_input_paths(paths), repo_root, allow_repo_paths, writer)
        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        run_dir_path = paths.run_dir
        if run_dir_path and qc_metrics is None:
            qc_path = run_dir_path / "metrics" / "qc.json"
            if qc_path.exists():
                qc_metrics = json.loads(qc_path.read_text(encoding="utf-8"))
        return RealInput(
            particles=particles,
            samples=samples,
            input_payload=_sanitize_payload(input_payload(paths), repo_root),
            input_config=paths.input_config,
            samples_generated=False,
            qc_metrics=qc_metrics if isinstance(qc_metrics, Mapping) else None,
        )

    particles_path = real_cfg.get("particles_path")
    if not particles_path:
        raise ValueError("coverage real_input requires particles_path or run_dir/manifest_path")
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
        qc_metrics=qc_metrics if isinstance(qc_metrics, Mapping) else None,
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
                f"pattern_coverage sample_id={sample_id} has mixed labels {sorted(label_counts.keys())}"
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


def _resolve_bins(
    coverage_cfg: Mapping[str, Any],
    wp_cfg: Mapping[str, Any],
    particles: list[Mapping[str, Any]],
) -> tuple[list[float], list[float], list[float]]:
    bins_cfg = _read_mapping(coverage_cfg.get("bins"), "coverage.bins", required=False)
    r_cfg = bins_cfg.get("r")
    theta_cfg = bins_cfg.get("theta")
    size_cfg = bins_cfg.get("size")

    if r_cfg is None or theta_cfg is None:
        qc_cfg = wp_cfg.get("qc")
        if isinstance(qc_cfg, Mapping):
            qc_bins = qc_cfg.get("bins")
            if isinstance(qc_bins, Mapping):
                r_cfg = r_cfg or qc_bins.get("r")
                theta_cfg = theta_cfg or qc_bins.get("theta")

    if r_cfg is None:
        r_cfg = {"start": 0.0, "stop": _max_value(particles, "r_mm", default=150.0), "count": 30}
    if theta_cfg is None:
        theta_cfg = {"start": 0.0, "stop": math.tau, "count": 36}

    r_edges = _resolve_edges(r_cfg, "coverage.bins.r")
    theta_edges = _resolve_edges(theta_cfg, "coverage.bins.theta")

    if size_cfg is None:
        size_min = _min_value(particles, "size_um", default=0.0)
        size_max = _max_value(particles, "size_um", default=10.0)
        if size_max <= size_min:
            size_max = size_min + 1.0
        size_cfg = {"start": size_min, "stop": size_max, "count": 20}
    size_edges = _resolve_edges(size_cfg, "coverage.bins.size")
    return r_edges, theta_edges, size_edges


def _resolve_epsilon(coverage_cfg: Mapping[str, Any]) -> float:
    score_cfg = coverage_cfg.get("score")
    if not isinstance(score_cfg, Mapping):
        return 1e-9
    epsilon = score_cfg.get("epsilon", 1e-9)
    epsilon = float(epsilon)
    if epsilon <= 0:
        raise ValueError("coverage.score.epsilon must be positive")
    return epsilon


def _resolve_weights(coverage_cfg: Mapping[str, Any]) -> dict[str, float]:
    score_cfg = coverage_cfg.get("score")
    if not isinstance(score_cfg, Mapping):
        score_cfg = {}
    weights_cfg = score_cfg.get("weights")
    if not isinstance(weights_cfg, Mapping):
        weights_cfg = {}
    defaults = {
        "hist_r_l1": 1.0,
        "hist_theta_l1": 1.0,
        "hist_size_l1": 1.0,
        "density_l1": 0.0,
    }
    resolved = dict(defaults)
    for key, value in weights_cfg.items():
        if key in resolved and value is not None:
            resolved[key] = float(value)
    return resolved


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
        raise ValueError("no labels available for pattern coverage")
    return label_defs


def _resolve_pattern_set(
    pattern_set: Any,
    label_defs: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    labels = sorted(label_defs.keys())
    if pattern_set is None or pattern_set == "all":
        return labels
    if not isinstance(pattern_set, list):
        raise ValueError("coverage.pattern_set must be a list when provided")
    chosen = [str(label) for label in pattern_set]
    missing = sorted({label for label in chosen if label not in label_defs})
    if missing:
        raise ValueError(f"coverage.pattern_set has unknown labels: {missing}")
    return chosen


def _sample_pattern_cfg(
    base_cfg: Mapping[str, Any],
    rng: np.random.Generator,
    label: str,
) -> dict[str, Any]:
    cfg = _deepcopy_mapping(base_cfg)
    param_space.apply_param_space(cfg, rng, path=f"wafer_particles.patterns.{label}")
    return cfg


def _generate_candidate_tables(
    *,
    label: str,
    pattern_cfg: Mapping[str, Any],
    seed: int,
    sample_id_prefix: str,
    particle_counts: Sequence[int],
    wafer_radius_mm: float,
    size_model_cfg: Mapping[str, Any],
    include_xy: bool,
    jitter_enabled: bool,
    jitter_r_std: float,
    jitter_theta_std: float,
    background_enabled: bool,
    background_count: int | None,
    background_fraction: float | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pattern_name = str(pattern_cfg.get("name", ""))
    if not pattern_name:
        raise ValueError("pattern name is required")
    particles: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for idx, n_particles in enumerate(particle_counts):
        sample_id = f"{sample_id_prefix}_{idx:06d}"
        ctx = resolve_sample_ctx(
            pattern_cfg,
            {"n_particles": int(n_particles), "wafer_radius_mm": wafer_radius_mm},
        )
        generator = get_pattern(pattern_name)
        pattern_rng = random.Random(_derive_seed(seed, idx, f"coverage:pattern:{label}"))
        sample_particles = _invoke_pattern(generator, ctx, pattern_cfg, pattern_rng)

        if jitter_enabled:
            jitter_rng = random.Random(_derive_seed(seed, idx, f"coverage:jitter:{label}"))
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
                background_rng = random.Random(_derive_seed(seed, idx, f"coverage:background:{label}"))
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
        size_rng = random.Random(_derive_seed(seed, idx, f"coverage:size_model:{label}"))
        apply_size_model(size_model_cfg, size_rng, sample_particles)
        if include_xy:
            _append_cartesian(sample_particles)

        samples.append(
            {
                "sample_id": sample_id,
                "label": label,
                "n_particles": len(sample_particles),
                "pattern_params": json.dumps(
                    _sanitize_params(pattern_cfg),
                    sort_keys=True,
                    ensure_ascii=True,
                ),
                "seed_offset": idx,
            }
        )
        particles.extend(sample_particles)

    validate_particles_table(particles)
    validate_samples_table(samples)
    return particles, samples


def _invoke_pattern(
    generator: Any,
    ctx: PatternContext,
    params: Mapping[str, Any],
    rng: random.Random,
) -> list[dict[str, Any]]:
    if hasattr(generator, "generate"):
        return generator.generate(ctx, params, rng)
    sample_ctx = {"n_particles": ctx.n_particles, "wafer_radius_mm": ctx.wafer_radius_mm}
    return generator(params, rng, sample_ctx)


def _finalize_particles(particles: list[dict[str, Any]], ctx: PatternContext) -> None:
    if not particles:
        return
    for particle in particles:
        theta_rad = float(particle["theta_rad"]) % math.tau
        particle["theta_rad"] = theta_rad

        if particle.get("r_norm") is None:
            if particle.get("r_mm") is None:
                raise ValueError("particle missing r_norm/r_mm")
            r_norm = float(particle["r_mm"]) / ctx.wafer_radius_mm
        else:
            r_norm = float(particle["r_norm"])
        if r_norm < 0.0 or r_norm > 1.0:
            r_norm = min(max(r_norm, 0.0), 1.0)
        particle["r_norm"] = r_norm
        particle["r_mm"] = norm_to_mm(r_norm, ctx.wafer_radius_mm)

        if "component" in particle and "component_label_fine" not in particle:
            particle["component_label_fine"] = str(particle["component"])
        if "component_label_fine" in particle and "component" not in particle:
            particle["component"] = str(particle["component_label_fine"])


def _append_cartesian(particles: list[dict[str, Any]]) -> None:
    for particle in particles:
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        x_mm, y_mm = polar_to_cartesian_mm(r_mm, theta_rad)
        particle["x_mm"] = float(x_mm)
        particle["y_mm"] = float(y_mm)


def _compute_reference_metrics(
    particles: list[dict[str, Any]],
    *,
    r_edges: list[float],
    theta_edges: list[float],
    size_edges: list[float],
) -> dict[str, Any]:
    r_values = _extract_values(particles, "r_mm")
    theta_values = _extract_values(particles, "theta_rad")
    size_values = _extract_values(particles, "size_um")

    hist_r, r_out = _compute_hist(r_values, r_edges)
    hist_theta, theta_out = _compute_hist(theta_values, theta_edges)
    hist_size, size_out = _compute_hist(size_values, size_edges)
    grid_counts, grid_out = _polar_grid_counts(particles, r_edges, theta_edges)
    size_stats = compute_size_stats(size_values)
    return {
        "hist_r": {"counts": hist_r, "out_of_range": r_out},
        "hist_theta": {"counts": hist_theta, "out_of_range": theta_out},
        "hist_size": {"counts": hist_size, "out_of_range": size_out},
        "grid_counts": {"counts": grid_counts, "out_of_range": grid_out},
        "size_stats": size_stats,
    }


def _compute_distance_metrics(
    particles: list[dict[str, Any]],
    *,
    real_metrics: Mapping[str, Any],
    r_edges: list[float],
    theta_edges: list[float],
    size_edges: list[float],
    epsilon: float,
) -> dict[str, Any]:
    r_values = _extract_values(particles, "r_mm")
    theta_values = _extract_values(particles, "theta_rad")
    size_values = _extract_values(particles, "size_um")

    hist_r, r_out = _compute_hist(r_values, r_edges)
    hist_theta, theta_out = _compute_hist(theta_values, theta_edges)
    hist_size, size_out = _compute_hist(size_values, size_edges)

    real_hist_r = _hist_counts(real_metrics.get("hist_r"))
    real_hist_theta = _hist_counts(real_metrics.get("hist_theta"))
    real_hist_size = _hist_counts(real_metrics.get("hist_size"))

    grid_counts, grid_out = _polar_grid_counts(particles, r_edges, theta_edges)
    real_grid_counts = _hist_counts(real_metrics.get("grid_counts"))

    size_stats = compute_size_stats(size_values)
    real_size_stats = real_metrics.get("size_stats", {})

    metrics = {
        "hist_r_l1": _hist_l1(real_hist_r, hist_r),
        "hist_theta_l1": _hist_l1(real_hist_theta, hist_theta),
        "hist_size_l1": _hist_l1(real_hist_size, hist_size),
        "density_l1": _density_l1(real_grid_counts, grid_counts, epsilon=epsilon),
        "size_mean_abs": _abs_diff(real_size_stats.get("mean"), size_stats.get("mean")),
        "size_std_abs": _abs_diff(real_size_stats.get("std"), size_stats.get("std")),
        "hist_r_out_of_range": r_out,
        "hist_theta_out_of_range": theta_out,
        "hist_size_out_of_range": size_out,
        "grid_out_of_range": grid_out,
    }
    return metrics


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


def _hist_counts(hist_payload: Any) -> list[int]:
    if not isinstance(hist_payload, Mapping):
        return []
    counts = hist_payload.get("counts")
    if not isinstance(counts, list):
        return []
    return [int(value) for value in counts]


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


def _polar_grid_counts(
    particles: Sequence[Mapping[str, Any]],
    r_edges: list[float],
    theta_edges: list[float],
) -> tuple[list[int], int]:
    r_bins = len(r_edges) - 1
    theta_bins = len(theta_edges) - 1
    counts = [0 for _ in range(r_bins * theta_bins)]
    out_of_range = 0
    for particle in particles:
        r_value = particle.get("r_mm")
        theta_value = particle.get("theta_rad")
        if r_value is None or theta_value is None:
            continue
        r_idx = _bin_index(float(r_value), r_edges)
        theta_idx = _bin_index(float(theta_value), theta_edges)
        if r_idx is None or theta_idx is None:
            out_of_range += 1
            continue
        counts[(r_idx * theta_bins) + theta_idx] += 1
    return counts, out_of_range


def _bin_index(value: float, edges: list[float]) -> int | None:
    if value < edges[0] or value > edges[-1]:
        return None
    if value == edges[-1]:
        return len(edges) - 2
    idx = _bisect_right(edges, value) - 1
    if idx < 0 or idx >= len(edges) - 1:
        return None
    return idx


def _bisect_right(edges: list[float], value: float) -> int:
    lo = 0
    hi = len(edges)
    while lo < hi:
        mid = (lo + hi) // 2
        if value < edges[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _density_l1(counts_a: list[int], counts_b: list[int], *, epsilon: float) -> float | None:
    if len(counts_a) != len(counts_b):
        return None
    probs_a = _smooth_probs(counts_a, epsilon)
    probs_b = _smooth_probs(counts_b, epsilon)
    if not probs_a or not probs_b:
        return None
    return sum(abs(a - b) for a, b in zip(probs_a, probs_b))


def _smooth_probs(counts: list[int], epsilon: float) -> list[float]:
    total = sum(counts)
    if total == 0:
        return []
    if epsilon > 0:
        counts = [value + epsilon for value in counts]
        total = sum(counts)
    return [value / total for value in counts]


def _decision_payload(best: Mapping[str, Any], kind: str, threshold: float) -> dict[str, Any]:
    score = float(best.get("score", 0.0))
    if score > threshold:
        action = "New pattern likely needed"
    elif kind == "composite":
        action = "Composite recipe recommended"
    else:
        action = "Existing pattern fits"
    return {
        "action": action,
        "best_score": score,
        "best_kind": kind,
        "threshold_new_pattern": threshold,
    }


def _write_markdown(path: Path, summary: Mapping[str, Any]) -> None:
    decision = summary.get("decision", {})
    results = summary.get("results", {})
    top_patterns = results.get("top_patterns", [])
    best = results.get("best", {})
    best_kind = results.get("best_kind", "")
    lines = [
        "# Coverage Summary",
        "",
        f"- decision: {decision.get('action')}",
        f"- best_kind: {best_kind}",
        f"- best_score: {decision.get('best_score')}",
        f"- threshold_new_pattern: {decision.get('threshold_new_pattern')}",
        "",
        "## Best Candidate",
        "",
        f"- label: {best.get('label')}",
        f"- pattern_id: {best.get('pattern_id')}",
        f"- score: {best.get('score')}",
        "",
        "## Top Patterns",
        "",
        "| rank | label | pattern_id | score | hist_r_l1 | hist_theta_l1 | hist_size_l1 | density_l1 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for idx, item in enumerate(top_patterns, start=1):
        metrics = item.get("metrics", {})
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    str(item.get("label")),
                    str(item.get("pattern_id")),
                    _fmt(item.get("score")),
                    _fmt(metrics.get("hist_r_l1")),
                    _fmt(metrics.get("hist_theta_l1")),
                    _fmt(metrics.get("hist_size_l1")),
                    _fmt(metrics.get("density_l1")),
                ]
            )
            + " |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _write_plots(
    writer,
    real_particles: list[dict[str, Any]],
    best_particles: list[dict[str, Any]] | None,
    r_edges: list[float],
    theta_edges: list[float],
    size_edges: list[float],
) -> None:
    plots_dir = writer.run_dir / "plots"
    if not best_particles:
        (plots_dir / "placeholder.txt").write_text(
            "plots are not generated for process=pattern_coverage\n",
            encoding="utf-8",
        )
        return
    try:
        plt = _get_pyplot()
    except RuntimeError as exc:
        writer.log(f"plotting skipped: {exc}")
        (plots_dir / "placeholder.txt").write_text(
            "plots are not generated for process=pattern_coverage\n",
            encoding="utf-8",
        )
        return

    plots_dir.mkdir(parents=True, exist_ok=True)
    real_r = _extract_values(real_particles, "r_mm")
    real_theta = _extract_values(real_particles, "theta_rad")
    real_size = _extract_values(real_particles, "size_um")
    best_r = _extract_values(best_particles, "r_mm")
    best_theta = _extract_values(best_particles, "theta_rad")
    best_size = _extract_values(best_particles, "size_um")

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    axes[0].hist(real_r, bins=r_edges, density=True, alpha=0.6, label="real", color="#4C72B0")
    axes[0].hist(best_r, bins=r_edges, density=True, alpha=0.6, label="best", color="#C44E52")
    axes[0].set_title("r_mm")
    axes[0].set_xlabel("r_mm")
    axes[0].set_ylabel("density")
    axes[0].legend()

    axes[1].hist(real_theta, bins=theta_edges, density=True, alpha=0.6, label="real", color="#4C72B0")
    axes[1].hist(best_theta, bins=theta_edges, density=True, alpha=0.6, label="best", color="#C44E52")
    axes[1].set_title("theta_rad")
    axes[1].set_xlabel("theta_rad")
    axes[1].set_ylabel("density")
    axes[1].legend()

    axes[2].hist(real_size, bins=size_edges, density=True, alpha=0.6, label="real", color="#4C72B0")
    axes[2].hist(best_size, bins=size_edges, density=True, alpha=0.6, label="best", color="#C44E52")
    axes[2].set_title("size_um")
    axes[2].set_xlabel("size_um")
    axes[2].set_ylabel("density")
    axes[2].legend()

    fig.tight_layout()
    fig.savefig(plots_dir / "coverage_real_vs_best_hist.png", dpi=150)
    plt.close(fig)

    real_grid, _ = _polar_grid_counts(real_particles, r_edges, theta_edges)
    best_grid, _ = _polar_grid_counts(best_particles, r_edges, theta_edges)
    residual = _density_residual(best_grid, real_grid)
    r_bins = len(r_edges) - 1
    theta_bins = len(theta_edges) - 1
    residual_grid = [
        residual[idx * theta_bins : (idx + 1) * theta_bins] for idx in range(r_bins)
    ]

    fig, ax = plt.subplots(1, 1, figsize=(6, 5))
    im = ax.imshow(
        residual_grid,
        aspect="auto",
        origin="lower",
        cmap="coolwarm",
    )
    ax.set_title("density residual (best - real)")
    ax.set_xlabel("theta bin")
    ax.set_ylabel("r bin")
    fig.colorbar(im, ax=ax, label="density delta")
    fig.tight_layout()
    fig.savefig(plots_dir / "coverage_residual_map.png", dpi=150)
    plt.close(fig)


def _get_pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError("matplotlib is required for coverage plots") from exc
    return plt


def _density_residual(counts_a: list[int], counts_b: list[int]) -> list[float]:
    if len(counts_a) != len(counts_b) or not counts_a:
        return []
    probs_a = _smooth_probs(counts_a, epsilon=0.0)
    probs_b = _smooth_probs(counts_b, epsilon=0.0)
    if not probs_a or not probs_b:
        return [0.0 for _ in counts_a]
    return [float(a - b) for a, b in zip(probs_a, probs_b)]


def _label_combinations(labels: list[str], k: int) -> Sequence[tuple[str, ...]]:
    if k <= 0:
        return []
    return list(_combinations(labels, k))


def _combinations(labels: Sequence[str], k: int) -> Sequence[tuple[str, ...]]:
    if k <= 0:
        return []
    if k == 1:
        return [(label,) for label in labels]
    combos = []
    for idx, label in enumerate(labels):
        for tail in _combinations(labels[idx + 1 :], k - 1):
            combos.append((label,) + tail)
    return combos


def _candidate_product(
    candidate_lists: Sequence[Sequence[dict[str, Any]]],
    limit: int,
) -> Sequence[tuple[dict[str, Any], ...]]:
    if not candidate_lists:
        return []
    combos: list[tuple[dict[str, Any], ...]] = [()]
    for candidates in candidate_lists:
        next_combos: list[tuple[dict[str, Any], ...]] = []
        for combo in combos:
            for candidate in candidates:
                next_combos.append(combo + (candidate,))
                if len(next_combos) >= limit:
                    break
            if len(next_combos) >= limit:
                break
        combos = next_combos
        if len(combos) >= limit:
            break
    return combos


def _build_composite_params(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    for candidate in candidates:
        pattern_id = candidate.get("pattern_id")
        params = candidate.get("params")
        if not pattern_id or not isinstance(params, Mapping):
            raise ValueError("invalid candidate for composite")
        component_cfg = dict(params)
        component_cfg.pop("name", None)
        components.append(
            {
                "pattern": str(pattern_id),
                "cfg": component_cfg,
                "weight": 1.0,
                "component_label_fine": str(candidate.get("label")),
            }
        )
    return {
        "name": "wafer_particles.pattern.composite",
        "components": components,
    }


def _resolve_size_model_cfg(wp_cfg: Mapping[str, Any]) -> dict[str, Any]:
    size_cfg = wp_cfg.get("size_models") or wp_cfg.get("size_model")
    if not isinstance(size_cfg, Mapping):
        raise ValueError("wafer_particles.size_models config is required")
    return _deepcopy_mapping(size_cfg)


def _resolve_wafer_radius_mm(wp_cfg: Mapping[str, Any], particles: list[Mapping[str, Any]]) -> float:
    wafer_radius_mm = wp_cfg.get("wafer_radius_mm")
    if wafer_radius_mm is not None:
        return float(wafer_radius_mm)
    return float(_max_value(particles, "r_mm", default=150.0))


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
    return enabled and (count is not None or fraction is not None), count, fraction


def _ensure_comparable(cfg: Mapping[str, Any], real_input: RealInput) -> None:
    expected_schema = str(cfg.get("schema_version", SCHEMA_VERSION))
    expected_domain = _domain_name(cfg)
    input_cfg = real_input.input_config
    if not input_cfg:
        return
    schema = input_cfg.get("schema_version")
    if schema and str(schema) != expected_schema:
        raise ValueError(f"schema_version mismatch for real input: {schema}")
    domain = _domain_name(input_cfg)
    if domain and domain != expected_domain:
        raise ValueError(f"domain mismatch for real input: {domain}")


def _sanitize_params(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize_params(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_params(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (Path,)):
        return str(value)
    return value


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


def _coerce_optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _coerce_positive_int(value, name)


def _coerce_int(value: Any, name: str) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an int") from exc


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


def _abs_diff(value_a: Any, value_b: Any) -> float | None:
    try:
        if value_a is None or value_b is None:
            return None
        return abs(float(value_a) - float(value_b))
    except (TypeError, ValueError):
        return None


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
    for key in ["run_dir", "manifest_path", "particles_path", "samples_path", "qc_metrics_path"]:
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


def _qc_metrics_path(qc_metrics: Mapping[str, Any] | None, repo_root: Path) -> str | None:
    if not qc_metrics:
        return None
    payload = qc_metrics.get("input")
    if not isinstance(payload, Mapping):
        return None
    qc_path = payload.get("qc_metrics_path")
    if not qc_path:
        return None
    return _sanitize_path(qc_path, repo_root)


def _allocate_counts(total: int, weights: Sequence[float]) -> list[int]:
    if total <= 0:
        return [0 for _ in weights]
    if not weights:
        return []
    if any(weight < 0 for weight in weights):
        raise ValueError("weights must be non-negative")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("weights must sum to > 0")
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


def _deepcopy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(value))


def _max_value(particles: list[Mapping[str, Any]], key: str, *, default: float) -> float:
    values = [float(row[key]) for row in particles if row.get(key) is not None]
    return max(values) if values else float(default)


def _min_value(particles: list[Mapping[str, Any]], key: str, *, default: float) -> float:
    values = [float(row[key]) for row in particles if row.get(key) is not None]
    return min(values) if values else float(default)


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
