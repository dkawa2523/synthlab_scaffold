from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.metrics.qc_metrics import (
    _angular_distance,
    _compute_label_stats,
    _parse_taxonomy,
    _read_mapping,
    _resolve_edges,
    _resolve_grid_bins,
    _resolve_qc_cfg,
    _resolve_quantiles,
    _resolve_wafer_radius_mm,
)
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import (
    InputPaths,
    input_payload,
    read_table,
    resolve_input_paths,
    resolve_path,
)


@dataclass(frozen=True)
class InputData:
    particles: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    input_payload: dict[str, Any]
    input_config: dict[str, Any] | None
    samples_generated: bool


@register_process("wafer_particles.process.compare_real")
class CompareRealProcess(BaseProcess):
    name = "wafer_particles.process.compare_real"

    def run(self, writer) -> None:
        writer.log("compare_real start")
        wp_cfg = _read_mapping(self.cfg.get("wafer_particles"), "wafer_particles")
        compare_cfg = _read_mapping(wp_cfg.get("compare_real"), "wafer_particles.compare_real")
        real_cfg = _read_mapping(compare_cfg.get("real"), "wafer_particles.compare_real.real")
        synth_cfg = _read_mapping(compare_cfg.get("synthetic"), "wafer_particles.compare_real.synthetic")
        qc_cfg = _resolve_qc_cfg(self.cfg)
        allow_repo_paths = _real_data_allow_repo_paths(self.cfg)

        real_data = _load_real_input(
            real_cfg,
            repo_root=writer.repo_root,
            writer=writer,
            allow_repo_paths=allow_repo_paths,
        )
        validate_particles_table(real_data.particles)
        validate_samples_table(real_data.samples)
        real_metrics = _compute_qc_payload(
            cfg=self.cfg,
            qc_cfg=qc_cfg,
            particles=real_data.particles,
            samples=real_data.samples,
            input_payload=real_data.input_payload,
            input_config=real_data.input_config,
        )
        real_metrics["input"]["samples_generated"] = real_data.samples_generated

        synth_metrics, synth_payload = _load_synthetic_metrics(
            self.cfg,
            qc_cfg,
            synth_cfg,
            repo_root=writer.repo_root,
        )

        _ensure_comparable(real_metrics, synth_metrics, expected_cfg=self.cfg)

        diff_payload = _build_diff_payload(
            real_metrics=real_metrics,
            synth_metrics=synth_metrics,
            real_input=real_data.input_payload,
            synth_input=synth_payload,
        )

        writer.write_json("metrics/real_metrics.json", real_metrics)
        writer.write_json("metrics/synth_vs_real_diff.json", diff_payload)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=compare_real\n",
            encoding="utf-8",
        )
        writer.log("compare_real complete")


def _load_real_input(
    real_cfg: Mapping[str, Any],
    *,
    repo_root: Path,
    writer,
    allow_repo_paths: bool,
) -> InputData:
    run_dir = real_cfg.get("run_dir")
    manifest_path = real_cfg.get("manifest_path")
    run_name = real_cfg.get("run_name")
    samples_path = real_cfg.get("samples_path")
    if run_dir or manifest_path or run_name or samples_path:
        try:
            paths = resolve_input_paths(
                real_cfg,
                repo_root=repo_root,
                default_process_name="wafer_particles.process.generate",
            )
        except ValueError as exc:
            raise ValueError("real input paths could not be resolved") from exc
        _enforce_real_data_paths(_real_input_paths(paths), repo_root, allow_repo_paths, writer)
        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        return InputData(
            particles=particles,
            samples=samples,
            input_payload=_sanitize_payload(input_payload(paths), repo_root),
            input_config=paths.input_config,
            samples_generated=False,
        )

    particles_path = real_cfg.get("particles_path")
    if not particles_path:
        raise ValueError("compare_real real input requires particles_path or run_dir/manifest_path")
    resolved_particles = resolve_path(particles_path, repo_root)
    _enforce_real_data_paths([resolved_particles], repo_root, allow_repo_paths, writer)
    if not resolved_particles.exists():
        raise ValueError("real particles file not found")
    particles = read_table(resolved_particles)
    samples, warnings = _samples_from_particles(particles)
    for warning in warnings:
        writer.log(warning)
    payload = {
        "run_dir": None,
        "manifest_path": None,
        "particles_path": str(resolved_particles),
        "samples_path": None,
        "samples_generated": True,
    }
    return InputData(
        particles=particles,
        samples=samples,
        input_payload=_sanitize_payload(payload, repo_root),
        input_config=None,
        samples_generated=True,
    )


def _load_synthetic_metrics(
    cfg: Mapping[str, Any],
    qc_cfg: Mapping[str, Any],
    synth_cfg: Mapping[str, Any],
    *,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    qc_metrics_path = synth_cfg.get("qc_metrics_path")
    if qc_metrics_path:
        path = resolve_path(qc_metrics_path, repo_root)
        metrics = _read_metrics(path)
        payload = {
            "qc_metrics_path": str(path),
            "run_dir": None,
            "manifest_path": None,
            "particles_path": None,
            "samples_path": None,
        }
        return metrics, _sanitize_payload(payload, repo_root)

    run_dir = _resolve_run_dir(synth_cfg, repo_root=repo_root)
    if run_dir is not None:
        qc_path = run_dir / "metrics" / "qc.json"
        if qc_path.exists():
            metrics = _read_metrics(qc_path)
            payload = metrics.get("input") if isinstance(metrics.get("input"), Mapping) else {}
            payload = {**payload, "run_dir": str(run_dir)}
            return metrics, _sanitize_payload(payload, repo_root)

    paths = resolve_input_paths(
        synth_cfg,
        repo_root=repo_root,
        default_process_name="wafer_particles.process.generate",
    )
    particles = read_table(paths.particles_path)
    samples = read_table(paths.samples_path)
    validate_particles_table(particles)
    validate_samples_table(samples)
    metrics = _compute_qc_payload(
        cfg=cfg,
        qc_cfg=qc_cfg,
        particles=particles,
        samples=samples,
        input_payload=input_payload(paths),
        input_config=paths.input_config,
    )
    return metrics, _sanitize_payload(input_payload(paths), repo_root)


def _resolve_run_dir(synth_cfg: Mapping[str, Any], *, repo_root: Path) -> Path | None:
    run_dir = synth_cfg.get("run_dir")
    if run_dir:
        return resolve_path(run_dir, repo_root)
    run_name = synth_cfg.get("run_name")
    if run_name:
        process_name = str(synth_cfg.get("process_name", "wafer_particles.process.generate"))
        return repo_root / "runs" / str(run_name) / process_name
    return None


def _read_metrics(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"metrics must be a mapping: {path}")
    return dict(data)


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
                f"compare_real sample_id={sample_id} has mixed labels {sorted(label_counts.keys())}"
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


def _compute_qc_payload(
    *,
    cfg: Mapping[str, Any],
    qc_cfg: Mapping[str, Any],
    particles: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    input_payload: dict[str, Any],
    input_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    bins_cfg = _read_mapping(qc_cfg.get("bins"), "wafer_particles.qc.bins")
    r_edges = _resolve_edges(bins_cfg.get("r"), "bins.r")
    theta_edges = _resolve_edges(bins_cfg.get("theta"), "bins.theta")

    quantiles = _resolve_quantiles(qc_cfg.get("quantiles"))
    spatial_cfg = _read_mapping(qc_cfg.get("spatial"), "wafer_particles.qc.spatial", required=False)
    grid_bins = _resolve_grid_bins(spatial_cfg)
    taxonomy = _parse_taxonomy(cfg)
    wafer_radius_mm = _resolve_wafer_radius_mm(qc_cfg, input_config, particles)

    label_stats, _label_rows, summary = _compute_label_stats(
        particles,
        samples,
        taxonomy,
        r_edges,
        theta_edges,
        quantiles,
        qc_cfg,
        wafer_radius_mm,
        spatial_cfg,
    )

    return {
        "schema_version": str(cfg.get("schema_version", SCHEMA_VERSION)),
        "domain": _domain_name(cfg),
        "input": dict(input_payload),
        "bins": {
            "r_edges": r_edges,
            "theta_edges": theta_edges,
        },
        "spatial": {
            "grid_bins": grid_bins,
        },
        "summary": summary,
        "labels": label_stats,
    }


def _ensure_comparable(
    real_metrics: Mapping[str, Any],
    synth_metrics: Mapping[str, Any],
    *,
    expected_cfg: Mapping[str, Any],
) -> None:
    expected_schema = str(expected_cfg.get("schema_version", SCHEMA_VERSION))
    expected_domain = _domain_name(expected_cfg)
    synth_schema = synth_metrics.get("schema_version")
    synth_domain = synth_metrics.get("domain")
    if synth_schema != expected_schema:
        raise ValueError(f"schema_version mismatch: {synth_schema}")
    if synth_domain != expected_domain:
        raise ValueError(f"domain mismatch: {synth_domain}")

    real_bins = _read_mapping(real_metrics.get("bins"), "real.metrics.bins")
    synth_bins = _read_mapping(synth_metrics.get("bins"), "synthetic.metrics.bins")
    if real_bins.get("r_edges") != synth_bins.get("r_edges"):
        raise ValueError("bins.r_edges mismatch between real and synthetic metrics")
    if real_bins.get("theta_edges") != synth_bins.get("theta_edges"):
        raise ValueError("bins.theta_edges mismatch between real and synthetic metrics")

    real_spatial = _read_mapping(real_metrics.get("spatial"), "real.metrics.spatial", required=False)
    synth_spatial = _read_mapping(synth_metrics.get("spatial"), "synthetic.metrics.spatial", required=False)
    if real_spatial.get("grid_bins") != synth_spatial.get("grid_bins"):
        raise ValueError("spatial.grid_bins mismatch between real and synthetic metrics")


def _build_diff_payload(
    *,
    real_metrics: Mapping[str, Any],
    synth_metrics: Mapping[str, Any],
    real_input: Mapping[str, Any],
    synth_input: Mapping[str, Any],
) -> dict[str, Any]:
    real_summary = _read_mapping(real_metrics.get("summary"), "real.metrics.summary", required=False)
    synth_summary = _read_mapping(synth_metrics.get("summary"), "synthetic.metrics.summary", required=False)
    bins = _read_mapping(real_metrics.get("bins"), "real.metrics.bins")
    r_edges = bins.get("r_edges", [])
    theta_edges = bins.get("theta_edges", [])
    r_bins = max(len(r_edges) - 1, 0)
    theta_bins = max(len(theta_edges) - 1, 0)

    real_labels = real_metrics.get("labels")
    synth_labels = synth_metrics.get("labels")
    if not isinstance(real_labels, Mapping) or not isinstance(synth_labels, Mapping):
        raise ValueError("metrics.labels must be a mapping")
    labels = sorted(set(real_labels.keys()) | set(synth_labels.keys()))

    label_diffs: dict[str, Any] = {}
    hist_r_l1_values: list[float] = []
    hist_theta_l1_values: list[float] = []
    size_mean_values: list[float] = []
    r_mean_values: list[float] = []
    theta_mean_values: list[float] = []

    for label in labels:
        real_info = real_labels.get(label, {})
        synth_info = synth_labels.get(label, {})
        real_hist_r = _hist_counts(real_info, "hist_r", r_bins)
        synth_hist_r = _hist_counts(synth_info, "hist_r", r_bins)
        real_hist_theta = _hist_counts(real_info, "hist_theta", theta_bins)
        synth_hist_theta = _hist_counts(synth_info, "hist_theta", theta_bins)

        hist_r_l1 = _hist_l1(real_hist_r, synth_hist_r)
        hist_theta_l1 = _hist_l1(real_hist_theta, synth_hist_theta)
        if hist_r_l1 is not None:
            hist_r_l1_values.append(hist_r_l1)
        if hist_theta_l1 is not None:
            hist_theta_l1_values.append(hist_theta_l1)

        size_mean = _abs_diff(
            _nested_value(real_info, ("size_stats", "mean")),
            _nested_value(synth_info, ("size_stats", "mean")),
        )
        r_mean = _abs_diff(
            _nested_value(real_info, ("r_stats", "mean")),
            _nested_value(synth_info, ("r_stats", "mean")),
        )
        theta_mean = _angular_diff(
            _nested_value(real_info, ("theta_stats", "mean")),
            _nested_value(synth_info, ("theta_stats", "mean")),
        )
        if size_mean is not None:
            size_mean_values.append(size_mean)
        if r_mean is not None:
            r_mean_values.append(r_mean)
        if theta_mean is not None:
            theta_mean_values.append(theta_mean)

        label_diffs[label] = {
            "n_particles_abs": _abs_diff(real_info.get("n_particles"), synth_info.get("n_particles")),
            "n_samples_abs": _abs_diff(real_info.get("n_samples"), synth_info.get("n_samples")),
            "hist_r_l1": hist_r_l1,
            "hist_theta_l1": hist_theta_l1,
            "size_mean_abs": size_mean,
            "r_mean_abs": r_mean,
            "theta_mean_abs": theta_mean,
        }

    diff_summary = {
        "total_particles_abs": _abs_diff(
            real_summary.get("total_particles"),
            synth_summary.get("total_particles"),
        ),
        "total_samples_abs": _abs_diff(
            real_summary.get("total_samples"),
            synth_summary.get("total_samples"),
        ),
        "rule_violations_abs": _abs_diff(
            real_summary.get("rule_violations"),
            synth_summary.get("rule_violations"),
        ),
    }

    overall = {
        "labels_compared": len(labels),
        "hist_r_l1_mean": _mean(hist_r_l1_values),
        "hist_theta_l1_mean": _mean(hist_theta_l1_values),
        "size_mean_abs_mean": _mean(size_mean_values),
        "r_mean_abs_mean": _mean(r_mean_values),
        "theta_mean_abs_mean": _mean(theta_mean_values),
    }

    return {
        "schema_version": real_metrics.get("schema_version"),
        "domain": real_metrics.get("domain"),
        "input": {
            "real": dict(real_input),
            "synthetic": dict(synth_input),
        },
        "bins": dict(bins),
        "summary": diff_summary,
        "overall": overall,
        "labels": label_diffs,
    }


def _hist_counts(info: Mapping[str, Any], key: str, length: int) -> list[int]:
    hist = info.get(key)
    if not isinstance(hist, Mapping):
        return [0] * length
    counts = hist.get("counts")
    if not isinstance(counts, list):
        return [0] * length
    padded = [int(value) for value in counts]
    if len(padded) < length:
        padded.extend([0] * (length - len(padded)))
    return padded[:length]


def _hist_l1(values_a: list[int], values_b: list[int]) -> float | None:
    if len(values_a) != len(values_b):
        return None
    total_a = sum(values_a)
    total_b = sum(values_b)
    if total_a == 0 and total_b == 0:
        return 0.0
    if total_a == 0 or total_b == 0:
        return 1.0
    norm_a = [value / total_a for value in values_a]
    norm_b = [value / total_b for value in values_b]
    return sum(abs(a - b) for a, b in zip(norm_a, norm_b))


def _nested_value(info: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    current: Any = info
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    if current is None:
        return None
    try:
        return float(current)
    except (TypeError, ValueError):
        return None


def _abs_diff(value_a: Any, value_b: Any) -> float | None:
    try:
        if value_a is None or value_b is None:
            return None
        return abs(float(value_a) - float(value_b))
    except (TypeError, ValueError):
        return None


def _angular_diff(value_a: Any, value_b: Any) -> float | None:
    try:
        if value_a is None or value_b is None:
            return None
        return _angular_distance(float(value_a), float(value_b))
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


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


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
