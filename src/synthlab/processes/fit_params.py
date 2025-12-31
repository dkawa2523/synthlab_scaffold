from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, log, sin, sqrt, tau
from pathlib import Path
from typing import Any, Iterable, Mapping

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    polar_to_cartesian_mm,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.metrics.qc_metrics import _parse_taxonomy, _resolve_wafer_radius_mm
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import get_param_estimator, register_process
from synthlab.processes._wafer_particles_io import input_payload, read_table, resolve_input_paths, resolve_path

import synthlab.domains.wafer_particles.param_estimators  # noqa: F401


@dataclass(frozen=True)
class InputData:
    particles: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    input_payload: dict[str, Any]
    input_config: dict[str, Any] | None
    samples_generated: bool


@register_process("wafer_particles.process.fit_params")
class FitParamsProcess(BaseProcess):
    name = "wafer_particles.process.fit_params"

    def run(self, writer) -> None:
        writer.log("fit_params start")
        fit_cfg = _resolve_fit_cfg(self.cfg)
        input_cfg = _read_mapping(fit_cfg.get("input"), "wafer_particles.fit_params.input", required=False)
        allow_repo_paths = _real_data_allow_repo_paths(self.cfg)
        input_data = _load_input(
            input_cfg,
            repo_root=writer.repo_root,
            writer=writer,
            allow_repo_paths=allow_repo_paths,
        )
        validate_particles_table(input_data.particles)
        validate_samples_table(input_data.samples)

        group_by_label = _coerce_bool(fit_cfg.get("group_by_label"), default=True)
        stats_cfg = _read_mapping(fit_cfg.get("stats"), "wafer_particles.fit_params.stats", required=False)
        estimator_map = _resolve_estimator_map(fit_cfg)
        estimator_cfgs = _read_mapping(
            fit_cfg.get("estimator_configs"),
            "wafer_particles.fit_params.estimator_configs",
            required=False,
        )
        taxonomy = _parse_taxonomy(self.cfg)
        wafer_radius_mm = _resolve_wafer_radius_mm(fit_cfg, input_data.input_config, input_data.particles)

        label_groups, group_mode = _group_particles(input_data.particles, group_by_label)
        sample_counts = _count_samples_by_label(input_data.samples)

        labels_payload: dict[str, Any] = {}
        total_particles = len(input_data.particles)
        for label in sorted(label_groups.keys()):
            particles = label_groups[label]
            stats, extras = _compute_particle_stats(
                particles,
                stats_cfg=stats_cfg,
                wafer_radius_mm=wafer_radius_mm,
                n_samples=sample_counts.get(label, 0),
            )
            meta = taxonomy.get(label, {})
            estimator_key = _resolve_estimator_key(label, meta, estimator_map)
            estimator = get_param_estimator(estimator_key)
            estimator_cfg = _resolve_estimator_cfg(estimator_key, estimator_cfgs)
            params = estimator(
                estimator_cfg,
                {
                    "stats": stats,
                    "wafer_radius_mm": wafer_radius_mm,
                    **extras,
                },
            )
            labels_payload[label] = {
                "estimator": estimator_key,
                "estimated_params": params,
                "stats": stats,
            }

        payload = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": _sanitize_payload(input_data.input_payload, writer.repo_root),
            "grouping": {"mode": group_mode},
            "summary": {
                "n_labels": len(labels_payload),
                "n_particles": total_particles,
                "n_samples": len(input_data.samples),
            },
            "labels": labels_payload,
        }
        writer.write_json("metrics/estimated_params.json", payload)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=fit_params\n",
            encoding="utf-8",
        )
        writer.log("fit_params complete")


def _resolve_fit_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    fit_cfg = wp_cfg.get("fit_params")
    if not isinstance(fit_cfg, Mapping):
        raise ValueError("wafer_particles.fit_params config is required")
    return dict(fit_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _load_input(
    input_cfg: Mapping[str, Any],
    *,
    repo_root: Path,
    writer,
    allow_repo_paths: bool,
) -> InputData:
    run_dir = input_cfg.get("run_dir")
    manifest_path = input_cfg.get("manifest_path")
    run_name = input_cfg.get("run_name")
    if run_dir or manifest_path or run_name:
        paths = resolve_input_paths(
            input_cfg,
            repo_root=repo_root,
            default_process_name="wafer_particles.process.generate",
        )
        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        return InputData(
            particles=particles,
            samples=samples,
            input_payload=input_payload(paths),
            input_config=paths.input_config,
            samples_generated=False,
        )

    particles_path = input_cfg.get("particles_path")
    if not particles_path:
        raise ValueError("fit_params input requires run_dir/manifest_path or particles_path")
    resolved_particles = resolve_path(particles_path, repo_root)
    samples_path = input_cfg.get("samples_path")
    resolved_samples = resolve_path(samples_path, repo_root) if samples_path else None
    _enforce_real_data_paths(
        [path for path in [resolved_particles, resolved_samples] if path is not None],
        repo_root,
        allow_repo_paths,
        writer,
    )
    if not resolved_particles.exists():
        raise ValueError("input particles file not found")
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
    return InputData(
        particles=particles,
        samples=samples,
        input_payload=payload,
        input_config=None,
        samples_generated=samples_generated,
    )


def _samples_from_particles(particles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
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
                f"fit_params sample_id={sample_id} has mixed labels {sorted(label_counts.keys())}"
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


def _group_particles(
    particles: list[dict[str, Any]],
    group_by_label: bool,
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    if not group_by_label:
        return {"all": particles}, "all"
    labels = [str(p.get("label") or "").strip() for p in particles]
    has_labels = any(label for label in labels)
    if not has_labels:
        return {"all": particles}, "all"
    grouped: dict[str, list[dict[str, Any]]] = {}
    for particle, label in zip(particles, labels):
        key = label or "unknown"
        grouped.setdefault(key, []).append(particle)
    return grouped, "label"


def _count_samples_by_label(samples: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        label = str(sample.get("label") or "").strip() or "unknown"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _compute_particle_stats(
    particles: list[dict[str, Any]],
    *,
    stats_cfg: Mapping[str, Any],
    wafer_radius_mm: float | None,
    n_samples: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    r_values: list[float] = []
    theta_values: list[float] = []
    points_xy: list[tuple[float, float]] = []
    for particle in particles:
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        r_values.append(r_mm)
        theta_values.append(theta_rad)
        x_mm = particle.get("x_mm")
        y_mm = particle.get("y_mm")
        if x_mm is None or y_mm is None:
            x_mm, y_mm = polar_to_cartesian_mm(r_mm, theta_rad)
        points_xy.append((float(x_mm), float(y_mm)))

    r_mean = _mean(r_values)
    r_std = _std(r_values, r_mean)
    r_min = min(r_values) if r_values else None
    r_max = max(r_values) if r_values else None
    r_quantiles = _resolve_quantiles(stats_cfg)
    quantile_values = _compute_quantiles(r_values, r_quantiles)

    theta_mean, theta_std = _circular_stats(theta_values)
    theta_bins = _resolve_theta_bins(stats_cfg)
    theta_hist, theta_centers = _theta_histogram(theta_values, theta_bins)
    theta_coverage = _theta_coverage(theta_hist, stats_cfg)
    theta_span_quantile = float(stats_cfg.get("theta_span_quantile", 0.9))
    theta_span = _theta_span(theta_values, theta_span_quantile)

    x_mean = _mean([x for x, _ in points_xy])
    y_mean = _mean([y for _, y in points_xy])

    stats: dict[str, Any] = {
        "n_particles": len(particles),
        "n_samples": n_samples,
        "r_mean_mm": r_mean,
        "r_std_mm": r_std,
        "r_min_mm": r_min,
        "r_max_mm": r_max,
        "r_quantiles": quantile_values,
        "theta_mean_rad": theta_mean,
        "theta_std_rad": theta_std,
        "theta_coverage": theta_coverage,
        "theta_span_rad": theta_span,
        "theta_span_quantile": theta_span_quantile,
        "theta_hist": theta_hist,
        "theta_bin_centers": theta_centers,
        "x_mean_mm": x_mean,
        "y_mean_mm": y_mean,
    }
    if wafer_radius_mm:
        stats["r_mean_ratio"] = r_mean / wafer_radius_mm if r_mean is not None else None
        stats["r_std_ratio"] = r_std / wafer_radius_mm if r_std is not None else None
    extras = {
        "points_xy": points_xy,
        "theta_values": theta_values,
    }
    return stats, extras


def _resolve_quantiles(stats_cfg: Mapping[str, Any]) -> list[float]:
    values = stats_cfg.get("r_quantiles")
    if values is None:
        return [0.05, 0.5, 0.95]
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes)):
        raise ValueError("fit_params.stats.r_quantiles must be a list")
    return [float(item) for item in values]


def _compute_quantiles(values: list[float], quantiles: list[float]) -> dict[str, float | None]:
    if not values:
        return {f"p{int(q * 100):02d}": None for q in quantiles}
    data = sorted(values)
    out: dict[str, float | None] = {}
    for q in quantiles:
        key = f"p{int(round(q * 100)):02d}"
        out[key] = _quantile(data, q)
    return out


def _quantile(data: list[float], q: float) -> float:
    if q <= 0.0:
        return data[0]
    if q >= 1.0:
        return data[-1]
    pos = q * (len(data) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(data) - 1)
    if lo == hi:
        return data[lo]
    frac = pos - lo
    return data[lo] + (data[hi] - data[lo]) * frac


def _mean(values: Iterable[float]) -> float | None:
    total = 0.0
    count = 0
    for value in values:
        total += float(value)
        count += 1
    if count == 0:
        return None
    return total / count


def _std(values: Iterable[float], mean_value: float | None) -> float | None:
    data = [float(value) for value in values]
    if not data or mean_value is None:
        return None
    variance = sum((value - mean_value) ** 2 for value in data) / len(data)
    return sqrt(variance)


def _circular_stats(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    sin_sum = sum(sin(theta) for theta in values)
    cos_sum = sum(cos(theta) for theta in values)
    if sin_sum == 0 and cos_sum == 0:
        return 0.0, None
    mean_angle = atan2(sin_sum, cos_sum)
    if mean_angle < 0:
        mean_angle += tau
    r = sqrt(sin_sum**2 + cos_sum**2) / len(values)
    if r <= 0:
        return mean_angle, None
    circ_std = sqrt(max(0.0, -2.0 * log(r))) if r < 1.0 else 0.0
    return mean_angle, circ_std


def _resolve_theta_bins(stats_cfg: Mapping[str, Any]) -> int:
    bins = stats_cfg.get("theta_bins", 36)
    bins = int(bins)
    if bins <= 0:
        raise ValueError("fit_params.stats.theta_bins must be positive")
    return bins


def _theta_histogram(values: list[float], bins: int) -> tuple[list[int], list[float]]:
    hist = [0 for _ in range(bins)]
    for theta in values:
        idx = int(((theta % tau) / tau) * bins)
        if idx >= bins:
            idx = bins - 1
        hist[idx] += 1
    centers = [(idx + 0.5) * tau / bins for idx in range(bins)]
    return hist, centers


def _theta_coverage(hist: list[int], stats_cfg: Mapping[str, Any]) -> float | None:
    if not hist:
        return None
    min_count = int(stats_cfg.get("theta_coverage_min_count", 1))
    covered = sum(1 for count in hist if count >= min_count)
    return covered / len(hist)


def _theta_span(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if quantile <= 0.0:
        return 0.0
    if quantile >= 1.0:
        return tau
    sorted_vals = sorted((theta % tau) for theta in values)
    n = len(sorted_vals)
    window = max(1, int(round(quantile * n)))
    extended = sorted_vals + [theta + tau for theta in sorted_vals]
    min_span = None
    for idx in range(n):
        span = extended[idx + window - 1] - extended[idx]
        if min_span is None or span < min_span:
            min_span = span
    return min_span


def _resolve_estimator_map(fit_cfg: Mapping[str, Any]) -> dict[str, str]:
    defaults = {
        "ring": "wafer_particles.param_estimator.ring",
        "sector": "wafer_particles.param_estimator.sector",
        "hotspot": "wafer_particles.param_estimator.hotspot",
        "scratch": "wafer_particles.param_estimator.scratch",
        "radial_lines": "wafer_particles.param_estimator.radial_lines",
        "line": "wafer_particles.param_estimator.scratch",
        "default": "wafer_particles.param_estimator.generic",
    }
    overrides = fit_cfg.get("estimators")
    if isinstance(overrides, Mapping):
        defaults.update({str(key): str(value) for key, value in overrides.items() if value})
    return defaults


def _resolve_estimator_key(label: str, meta: Mapping[str, Any], mapping: Mapping[str, str]) -> str:
    category = None
    for key in ["category", "coarse", "family"]:
        value = meta.get(key)
        if value:
            category = str(value)
            break
    label_lower = label.lower()
    if category == "line":
        if "radial" in label_lower:
            return mapping.get("radial_lines", mapping.get("line", mapping["default"]))
        if "scratch" in label_lower:
            return mapping.get("scratch", mapping.get("line", mapping["default"]))
        return mapping.get("line", mapping["default"])
    if category and category in mapping:
        return mapping[category]
    if "radial" in label_lower:
        return mapping.get("radial_lines", mapping["default"])
    if "scratch" in label_lower:
        return mapping.get("scratch", mapping["default"])
    if "ring" in label_lower:
        return mapping.get("ring", mapping["default"])
    if "sector" in label_lower:
        return mapping.get("sector", mapping["default"])
    if "hotspot" in label_lower:
        return mapping.get("hotspot", mapping["default"])
    return mapping["default"]


def _resolve_estimator_cfg(
    estimator_key: str,
    configs: Mapping[str, Any],
) -> dict[str, Any]:
    cfg = configs.get(estimator_key)
    if isinstance(cfg, Mapping):
        return dict(cfg)
    return {}


def _real_data_allow_repo_paths(cfg: Mapping[str, Any]) -> bool:
    policy_cfg = cfg.get("policy")
    if isinstance(policy_cfg, Mapping):
        real_cfg = policy_cfg.get("real_data")
        if isinstance(real_cfg, Mapping):
            return _coerce_bool(real_cfg.get("allow_repo_paths"), default=False)
    return False


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
