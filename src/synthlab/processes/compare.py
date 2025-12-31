from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from math import log, sqrt
from pathlib import Path
from typing import Any, Mapping, Sequence

import random

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    polar_to_cartesian_mm,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.metrics.qc_metrics import (
    _bisect_right,
    _compute_hist,
    _nearest_neighbor_distances,
    _read_mapping,
    _resolve_edges,
)
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import input_payload, read_table, resolve_input_paths


@dataclass(frozen=True)
class CompareInput:
    particles: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    payload: dict[str, Any]
    input_config: dict[str, Any] | None
    run_dir: Path | None


@register_process("wafer_particles.process.compare")
class CompareProcess(BaseProcess):
    name = "wafer_particles.process.compare"

    def run(self, writer) -> None:
        writer.log("compare start")
        compare_cfg = _resolve_compare_cfg(self.cfg)
        process_name = str(compare_cfg.get("process_name", "wafer_particles.process.generate"))

        bins_cfg = _read_mapping(compare_cfg.get("bins"), "compare.bins")
        r_edges = _resolve_edges(bins_cfg.get("r"), "compare.bins.r")
        theta_edges = _resolve_edges(bins_cfg.get("theta"), "compare.bins.theta")
        epsilon = _resolve_epsilon(compare_cfg.get("smoothing"))

        spatial_cfg = _read_mapping(compare_cfg.get("spatial"), "compare.spatial", required=False)
        nn_max_points = _coerce_optional_positive_int(
            spatial_cfg.get("nn_max_points"),
            "compare.spatial.nn_max_points",
        )

        input_a = _load_compare_input(
            compare_cfg,
            "a",
            repo_root=writer.repo_root,
            default_process_name=process_name,
        )
        input_b = _load_compare_input(
            compare_cfg,
            "b",
            repo_root=writer.repo_root,
            default_process_name=process_name,
        )

        _ensure_comparable(self.cfg, input_a, input_b)

        r_values_a = _extract_values(input_a.particles, "r_mm")
        r_values_b = _extract_values(input_b.particles, "r_mm")
        theta_values_a = _extract_values(input_a.particles, "theta_rad")
        theta_values_b = _extract_values(input_b.particles, "theta_rad")
        size_values_a = _extract_values(input_a.particles, "size_um")
        size_values_b = _extract_values(input_b.particles, "size_um")

        hist_r_a, _ = _compute_hist(r_values_a, r_edges)
        hist_r_b, _ = _compute_hist(r_values_b, r_edges)
        hist_theta_a, _ = _compute_hist(theta_values_a, theta_edges)
        hist_theta_b, _ = _compute_hist(theta_values_b, theta_edges)

        r_hist_js = _js_divergence(hist_r_a, hist_r_b, epsilon=epsilon)
        r_hist_kl = _kl_divergence(hist_r_a, hist_r_b, epsilon=epsilon)
        theta_hist_js = _js_divergence(hist_theta_a, hist_theta_b, epsilon=epsilon)

        size_ks = _ks_statistic(size_values_a, size_values_b)
        size_wasserstein = _wasserstein_distance(size_values_a, size_values_b)

        grid_counts_a, _ = _polar_grid_counts(input_a.particles, r_edges, theta_edges)
        grid_counts_b, _ = _polar_grid_counts(input_b.particles, r_edges, theta_edges)
        density_l1, density_l2 = _density_distances(
            grid_counts_a,
            grid_counts_b,
            epsilon=epsilon,
        )

        seed = _coerce_int(self.cfg.get("seed"), "seed")
        rng_a = random.Random(_derive_seed(seed, 0, "compare_nn"))
        rng_b = random.Random(_derive_seed(seed, 0, "compare_nn"))
        points_a = _collect_sample_points(input_a.particles, max_points=nn_max_points, rng=rng_a)
        points_b = _collect_sample_points(input_b.particles, max_points=nn_max_points, rng=rng_b)
        nn_dist_a = _nearest_neighbor_distances(points_a)
        nn_dist_b = _nearest_neighbor_distances(points_b)
        nn_distance_ks = _ks_statistic(nn_dist_a, nn_dist_b)

        summary = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": {"a": input_a.payload, "b": input_b.payload},
            "bins": {"r_edges": r_edges, "theta_edges": theta_edges},
            "n_particles_a": len(input_a.particles),
            "n_particles_b": len(input_b.particles),
            "n_samples_a": len(input_a.samples),
            "n_samples_b": len(input_b.samples),
            "r_hist_js": r_hist_js,
            "r_hist_kl": r_hist_kl,
            "theta_hist_js": theta_hist_js,
            "size_ks": size_ks,
            "size_wasserstein": size_wasserstein,
            "density_l1": density_l1,
            "density_l2": density_l2,
            "nn_distance_ks": nn_distance_ks,
        }
        writer.write_json("metrics/compare_summary.json", summary)
        _write_compare_table(writer.run_dir / "metrics" / "compare_table.csv", summary)
        _write_compare_plots(
            writer,
            r_values_a,
            r_values_b,
            theta_values_a,
            theta_values_b,
            size_values_a,
            size_values_b,
            r_edges,
            theta_edges,
        )
        writer.log("compare complete")


def _resolve_compare_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    compare_cfg = cfg.get("compare")
    if isinstance(compare_cfg, Mapping):
        return dict(compare_cfg)
    wp_cfg = cfg.get("wafer_particles")
    if isinstance(wp_cfg, Mapping) and isinstance(wp_cfg.get("compare"), Mapping):
        return dict(wp_cfg["compare"])
    raise ValueError("compare config is required")


def _resolve_epsilon(smoothing_cfg: Any) -> float:
    epsilon = 1e-9
    if isinstance(smoothing_cfg, Mapping) and smoothing_cfg.get("epsilon") is not None:
        epsilon = float(smoothing_cfg["epsilon"])
    if epsilon <= 0:
        raise ValueError("smoothing.epsilon must be positive")
    return epsilon


def _load_compare_input(
    compare_cfg: Mapping[str, Any],
    key: str,
    *,
    repo_root: Path,
    default_process_name: str,
) -> CompareInput:
    run_key = f"{key}_run"
    run_dir = compare_cfg.get(run_key)
    input_cfg = compare_cfg.get(key)
    if input_cfg is None:
        input_cfg = {}
    if not isinstance(input_cfg, Mapping):
        raise ValueError(f"compare.{key} must be a mapping when provided")
    resolved_cfg = dict(input_cfg)
    if run_dir is not None:
        resolved_cfg["run_dir"] = run_dir
    if "process_name" not in resolved_cfg and compare_cfg.get("process_name"):
        resolved_cfg["process_name"] = compare_cfg.get("process_name")

    if not _has_input(resolved_cfg):
        raise ValueError(f"compare.{run_key} is required")

    paths = resolve_input_paths(
        resolved_cfg,
        repo_root=repo_root,
        default_process_name=default_process_name,
    )
    particles = read_table(paths.particles_path)
    samples = read_table(paths.samples_path)
    if not particles:
        raise ValueError(f"compare {key} particles table is empty")
    if not samples:
        raise ValueError(f"compare {key} samples table is empty")
    validate_particles_table(particles)
    validate_samples_table(samples)
    payload = _sanitize_payload(input_payload(paths), repo_root)
    return CompareInput(
        particles=particles,
        samples=samples,
        payload=payload,
        input_config=paths.input_config,
        run_dir=paths.run_dir,
    )


def _has_input(cfg: Mapping[str, Any]) -> bool:
    if cfg.get("run_dir") or cfg.get("run_name") or cfg.get("manifest_path"):
        return True
    return bool(cfg.get("particles_path") and cfg.get("samples_path"))


def _ensure_comparable(
    cfg: Mapping[str, Any],
    input_a: CompareInput,
    input_b: CompareInput,
) -> None:
    expected_schema = str(cfg.get("schema_version", SCHEMA_VERSION))
    expected_domain = _domain_name(cfg)
    for label, input_data in (("a", input_a), ("b", input_b)):
        input_cfg = input_data.input_config
        if not input_cfg:
            continue
        schema = input_cfg.get("schema_version")
        if schema and str(schema) != expected_schema:
            raise ValueError(f"schema_version mismatch for {label}: {schema}")
        domain = _domain_name(input_cfg)
        if domain and domain != expected_domain:
            raise ValueError(f"domain mismatch for {label}: {domain}")


def _extract_values(particles: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for particle in particles:
        value = particle.get(key)
        if value is None:
            continue
        values.append(float(value))
    return values


def _js_divergence(counts_a: list[int], counts_b: list[int], *, epsilon: float) -> float | None:
    if len(counts_a) != len(counts_b):
        return None
    p = _smooth_probs(counts_a, epsilon)
    q = _smooth_probs(counts_b, epsilon)
    if not p or not q:
        return None
    m = [(pa + qb) * 0.5 for pa, qb in zip(p, q)]
    return 0.5 * (_kl_probs(p, m) + _kl_probs(q, m))


def _kl_divergence(counts_a: list[int], counts_b: list[int], *, epsilon: float) -> float | None:
    if len(counts_a) != len(counts_b):
        return None
    p = _smooth_probs(counts_a, epsilon)
    q = _smooth_probs(counts_b, epsilon)
    if not p or not q:
        return None
    return _kl_probs(p, q)


def _smooth_probs(counts: list[int], epsilon: float) -> list[float]:
    if not counts:
        return []
    smoothed = [float(value) + epsilon for value in counts]
    total = sum(smoothed)
    if total <= 0:
        return [1.0 / len(smoothed) for _ in smoothed]
    return [value / total for value in smoothed]


def _kl_probs(p: list[float], q: list[float]) -> float:
    return sum(pi * log(pi / qi) for pi, qi in zip(p, q))


def _ks_statistic(values_a: list[float], values_b: list[float]) -> float | None:
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


def _wasserstein_distance(values_a: list[float], values_b: list[float]) -> float | None:
    if not values_a and not values_b:
        return 0.0
    if not values_a or not values_b:
        return None
    a = sorted(values_a)
    b = sorted(values_b)
    n = len(a)
    m = len(b)
    weight_a = 1.0 / n
    weight_b = 1.0 / m
    i = 0
    j = 0
    cdf_a = 0.0
    cdf_b = 0.0
    prev = min(a[0], b[0])
    distance = 0.0
    while i < n or j < m:
        if j >= m:
            value = a[i]
        elif i >= n:
            value = b[j]
        else:
            value = a[i] if a[i] <= b[j] else b[j]
        distance += abs(cdf_a - cdf_b) * (value - prev)
        while i < n and a[i] == value:
            i += 1
            cdf_a = i * weight_a
        while j < m and b[j] == value:
            j += 1
            cdf_b = j * weight_b
        prev = value
    return distance


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


def _density_distances(
    counts_a: list[int],
    counts_b: list[int],
    *,
    epsilon: float,
) -> tuple[float | None, float | None]:
    if len(counts_a) != len(counts_b):
        return None, None
    p = _smooth_probs(counts_a, epsilon)
    q = _smooth_probs(counts_b, epsilon)
    if not p or not q:
        return None, None
    l1 = sum(abs(pa - qb) for pa, qb in zip(p, q))
    l2 = sqrt(sum((pa - qb) ** 2 for pa, qb in zip(p, q)))
    return l1, l2


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


def _write_compare_table(path: Path, summary: Mapping[str, Any]) -> None:
    rows = [
        ("r_hist_js", summary.get("r_hist_js")),
        ("r_hist_kl", summary.get("r_hist_kl")),
        ("theta_hist_js", summary.get("theta_hist_js")),
        ("size_ks", summary.get("size_ks")),
        ("size_wasserstein", summary.get("size_wasserstein")),
        ("density_l1", summary.get("density_l1")),
        ("density_l2", summary.get("density_l2")),
        ("nn_distance_ks", summary.get("nn_distance_ks")),
        ("n_particles_a", summary.get("n_particles_a")),
        ("n_particles_b", summary.get("n_particles_b")),
        ("n_samples_a", summary.get("n_samples_a")),
        ("n_samples_b", summary.get("n_samples_b")),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        for metric, value in rows:
            writer.writerow({"metric": metric, "value": _format_value(value)})


def _write_compare_plots(
    writer,
    r_values_a: Sequence[float],
    r_values_b: Sequence[float],
    theta_values_a: Sequence[float],
    theta_values_b: Sequence[float],
    size_values_a: Sequence[float],
    size_values_b: Sequence[float],
    r_edges: Sequence[float],
    theta_edges: Sequence[float],
) -> None:
    try:
        _ensure_mpl_config_dir(writer.repo_root)
        plt = _get_pyplot()
    except Exception as exc:
        writer.log(f"compare plots skipped: {exc}")
        return

    size_edges = _auto_edges(size_values_a + size_values_b, default_count=20)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    axes[0].hist(r_values_a, bins=r_edges, density=True, alpha=0.6, label="A", color="#4C72B0")
    axes[0].hist(r_values_b, bins=r_edges, density=True, alpha=0.6, label="B", color="#C44E52")
    axes[0].set_title("r_mm")
    axes[0].set_xlabel("r_mm")
    axes[0].set_ylabel("density")
    axes[0].legend(loc="upper right", fontsize="small")

    axes[1].hist(
        theta_values_a,
        bins=theta_edges,
        density=True,
        alpha=0.6,
        label="A",
        color="#4C72B0",
    )
    axes[1].hist(
        theta_values_b,
        bins=theta_edges,
        density=True,
        alpha=0.6,
        label="B",
        color="#C44E52",
    )
    axes[1].set_title("theta_rad")
    axes[1].set_xlabel("theta_rad")
    axes[1].set_ylabel("density")
    axes[1].legend(loc="upper right", fontsize="small")

    axes[2].hist(
        size_values_a,
        bins=size_edges,
        density=True,
        alpha=0.6,
        label="A",
        color="#4C72B0",
    )
    axes[2].hist(
        size_values_b,
        bins=size_edges,
        density=True,
        alpha=0.6,
        label="B",
        color="#C44E52",
    )
    axes[2].set_title("size_um")
    axes[2].set_xlabel("size_um")
    axes[2].set_ylabel("density")
    axes[2].legend(loc="upper right", fontsize="small")

    fig.tight_layout()
    out_path = writer.run_dir / "plots" / "compare_hist.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _auto_edges(values: Sequence[float], *, default_count: int) -> list[float]:
    if not values:
        return [0.0, 1.0]
    low = min(values)
    high = max(values)
    if low == high:
        return [low, high + 1.0]
    step = (high - low) / default_count
    return [low + step * idx for idx in range(default_count + 1)]


def _ensure_mpl_config_dir(repo_root: Path) -> Path:
    import os

    env_value = os.environ.get("MPLCONFIGDIR")
    if env_value:
        return Path(env_value)
    cfg_dir = repo_root / ".mplconfig"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cfg_dir)
    return cfg_dir


def _get_pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError("matplotlib is required for compare plots") from exc
    return plt


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def _sanitize_payload(payload: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    sanitized = dict(payload)
    for key in ["run_dir", "manifest_path", "particles_path", "samples_path"]:
        sanitized[key] = _sanitize_path(payload.get(key), repo_root)
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


def _derive_seed(base_seed: int, offset: int, component: str) -> int:
    payload = f"{base_seed}:{offset}:{component}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(base_seed) + int(digest[:12], 16)


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
