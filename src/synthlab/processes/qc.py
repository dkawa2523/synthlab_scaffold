from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from math import atan2, cos, log, pi, sin, sqrt, tau
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    polar_to_cartesian_mm,
    validate_manifest,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.metrics.size_stats import (
    DEFAULT_QUANTILES,
    compute_size_stats,
)
from synthlab.framework.artifacts import ArtifactReader
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process

_SIDE_TO_CENTER_RAD = {
    "right": 0.0,
    "top": tau / 4.0,
    "left": tau / 2.0,
    "bottom": 3.0 * tau / 4.0,
}


@dataclass(frozen=True)
class InputPaths:
    run_dir: Path | None
    manifest_path: Path | None
    particles_path: Path
    samples_path: Path
    input_config: dict[str, Any] | None


@register_process("wafer_particles.process.qc")
class QcProcess(BaseProcess):
    name = "wafer_particles.process.qc"

    def run(self, writer) -> None:
        writer.log("qc start")
        qc_cfg = _resolve_qc_cfg(self.cfg)
        paths = _resolve_input_paths(qc_cfg, repo_root=writer.repo_root)

        particles = _read_table(paths.particles_path)
        samples = _read_table(paths.samples_path)
        validate_particles_table(particles)
        validate_samples_table(samples)

        bins_cfg = _read_mapping(qc_cfg.get("bins"), "wafer_particles.qc.bins")
        r_edges = _resolve_edges(bins_cfg.get("r"), "bins.r")
        theta_edges = _resolve_edges(bins_cfg.get("theta"), "bins.theta")

        quantiles = _resolve_quantiles(qc_cfg.get("quantiles"))
        spatial_cfg = _read_mapping(qc_cfg.get("spatial"), "wafer_particles.qc.spatial", required=False)
        grid_bins = _resolve_grid_bins(spatial_cfg)
        taxonomy = _parse_taxonomy(self.cfg)
        wafer_radius_mm = _resolve_wafer_radius_mm(
            qc_cfg,
            paths.input_config,
            particles,
        )

        label_stats, label_rows, summary = _compute_label_stats(
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

        payload = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": _input_payload(paths),
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
        writer.write_json("metrics/qc.json", payload)
        _write_label_summary(writer.run_dir / "metrics" / "label_summary.csv", label_rows)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=qc\n",
            encoding="utf-8",
        )
        writer.log("qc complete")


def _resolve_qc_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    qc_cfg = wp_cfg.get("qc")
    if not isinstance(qc_cfg, Mapping):
        raise ValueError("wafer_particles.qc config is required")
    return dict(qc_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _resolve_quantiles(value: Any) -> list[float]:
    if value is None:
        return list(DEFAULT_QUANTILES)
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise ValueError("quantiles must be a list")
    return [float(item) for item in value]


def _resolve_edges(cfg: Any, name: str) -> list[float]:
    if cfg is None:
        raise ValueError(f"{name} config is required")
    if isinstance(cfg, Mapping) and "edges" in cfg:
        edges = [float(value) for value in cfg["edges"]]
    elif isinstance(cfg, Mapping):
        start = cfg.get("start")
        stop = cfg.get("stop")
        count = cfg.get("count")
        if start is None or stop is None or count is None:
            raise ValueError(f"{name} must define edges or start/stop/count")
        edges = _linspace(float(start), float(stop), int(count))
    else:
        raise ValueError(f"{name} must be a mapping")
    if len(edges) < 2:
        raise ValueError(f"{name} must have at least 2 edges")
    if any(edges[i] >= edges[i + 1] for i in range(len(edges) - 1)):
        raise ValueError(f"{name} edges must be strictly increasing")
    return edges


def _linspace(start: float, stop: float, count: int) -> list[float]:
    if count <= 0:
        raise ValueError("count must be positive")
    step = (stop - start) / count
    return [start + step * idx for idx in range(count + 1)]


def _resolve_input_paths(qc_cfg: Mapping[str, Any], *, repo_root: Path) -> InputPaths:
    input_cfg = _read_mapping(qc_cfg.get("input"), "wafer_particles.qc.input")
    run_dir = input_cfg.get("run_dir")
    manifest_path = input_cfg.get("manifest_path")
    particles_path = input_cfg.get("particles_path")
    samples_path = input_cfg.get("samples_path")
    input_config: dict[str, Any] | None = None

    if run_dir:
        run_dir = _resolve_path(run_dir, repo_root)
    else:
        run_name = input_cfg.get("run_name")
        if run_name:
            process_name = str(input_cfg.get("process_name", "wafer_particles.process.generate"))
            run_dir = repo_root / "runs" / str(run_name) / process_name

    if run_dir is not None:
        if not run_dir.exists():
            raise ValueError(f"input run_dir not found: {run_dir}")
        reader = ArtifactReader(run_dir=run_dir)
        config_path = run_dir / "config" / "resolved.yaml"
        if config_path.exists():
            input_config = reader.read_config()
        manifest_path = _find_manifest(run_dir)
        if manifest_path:
            particles_path, samples_path = _paths_from_manifest(
                manifest_path,
                expected_schema_version=SCHEMA_VERSION,
                expected_domain=DOMAIN_NAME,
            )
        else:
            particles_path = _resolve_data_path(run_dir, particles_path, ["particles.parquet", "particles.csv"])
            samples_path = _resolve_data_path(run_dir, samples_path, ["samples.parquet", "samples.csv"])
    elif manifest_path:
        manifest_path = _resolve_path(manifest_path, repo_root)
        particles_path, samples_path = _paths_from_manifest(
            manifest_path,
            expected_schema_version=SCHEMA_VERSION,
            expected_domain=DOMAIN_NAME,
        )
    else:
        if not particles_path or not samples_path:
            raise ValueError("qc input requires run_dir, manifest_path, or particles_path+samples_path")
        particles_path = _resolve_path(particles_path, repo_root)
        samples_path = _resolve_path(samples_path, repo_root)

    if particles_path is None or samples_path is None:
        raise ValueError("qc input paths could not be resolved")
    if not particles_path.exists():
        raise ValueError(f"particles file not found: {particles_path}")
    if not samples_path.exists():
        raise ValueError(f"samples file not found: {samples_path}")

    return InputPaths(
        run_dir=run_dir,
        manifest_path=manifest_path,
        particles_path=particles_path,
        samples_path=samples_path,
        input_config=input_config,
    )


def _resolve_path(value: Any, base: Path) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path


def _resolve_data_path(run_dir: Path, value: Any, candidates: list[str]) -> Path:
    if value:
        path = Path(str(value))
        if not path.is_absolute():
            return run_dir / path
        return path
    for name in candidates:
        path = run_dir / "data" / name
        if path.exists():
            return path
    raise ValueError(f"missing data file in {run_dir}")


def _find_manifest(run_dir: Path) -> Path | None:
    for name in ["manifest.json", "manifest.yaml", "manifest.yml"]:
        path = run_dir / name
        if path.exists():
            return path
    return None


def _paths_from_manifest(
    manifest_path: Path,
    *,
    expected_schema_version: str,
    expected_domain: str,
) -> tuple[Path, Path]:
    manifest = _read_manifest(manifest_path)
    validate_manifest(
        manifest,
        expected_schema_version=expected_schema_version,
        expected_domain=expected_domain,
    )
    base_dir = manifest_path.parent
    files = manifest["files"]
    particles = base_dir / str(files["particles"]["path"])
    samples = base_dir / str(files["samples"]["path"])
    return particles, samples


def _read_manifest(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"manifest must be a mapping: {path}")
    return dict(data)


def _read_table(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return _read_csv(path)
    if path.suffix.lower() == ".parquet":
        return _read_parquet(path)
    raise ValueError(f"unsupported table format: {path.suffix}")


def _read_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(_coerce_row(row))
    return rows


def _coerce_row(row: Mapping[str, Any]) -> dict[str, Any]:
    typed: dict[str, Any] = {}
    for key, value in row.items():
        if value is None or value == "":
            typed[key] = None
            continue
        if key in {"particle_id", "n_particles", "seed_offset"}:
            typed[key] = int(value)
        elif key in {"r_mm", "theta_rad", "size_um", "x_mm", "y_mm"}:
            typed[key] = float(value)
        else:
            typed[key] = str(value)
    return typed


def _read_parquet(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except Exception as exc:
        raise RuntimeError(
            "pyarrow is required for parquet input (use CSV if unavailable)."
        ) from exc
    table = pq.read_table(path)
    data = table.to_pydict()
    rows: list[dict[str, Any]] = []
    for idx in range(table.num_rows):
        rows.append({col: data[col][idx] for col in data})
    return rows


def _parse_taxonomy(cfg: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        return {}
    labels_cfg = wp_cfg.get("labels")
    if not isinstance(labels_cfg, Mapping):
        return {}
    entries = labels_cfg.get("labels")
    if not isinstance(entries, list):
        return {}
    label_map: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        base_name = entry.get("name")
        if not base_name:
            continue
        base_name = str(base_name)
        base_category = entry.get("category")
        base_rules = _ensure_list(entry.get("expected_rules"))
        base_params = _ensure_mapping(entry.get("params"))
        label_map[base_name] = {
            "category": str(base_category) if base_category else None,
            "expected_rules": base_rules,
            "params": base_params,
        }
        variants = entry.get("variants") or []
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, Mapping):
                continue
            name = variant.get("name")
            if not name:
                continue
            params = _ensure_mapping(variant.get("params"))
            expected_rules = _ensure_list(variant.get("expected_rules")) or base_rules
            merged_params = dict(base_params)
            merged_params.update(params)
            label_map[str(name)] = {
                "category": str(base_category) if base_category else None,
                "expected_rules": expected_rules,
                "params": merged_params,
            }
    return label_map


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _ensure_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _resolve_wafer_radius_mm(
    qc_cfg: Mapping[str, Any],
    input_cfg: Mapping[str, Any] | None,
    particles: list[Mapping[str, Any]],
) -> float | None:
    if "wafer_radius_mm" in qc_cfg and qc_cfg.get("wafer_radius_mm") is not None:
        return float(qc_cfg["wafer_radius_mm"])
    if input_cfg is not None:
        wp_cfg = input_cfg.get("wafer_particles")
        if isinstance(wp_cfg, Mapping):
            if wp_cfg.get("wafer_radius_mm") is not None:
                return float(wp_cfg["wafer_radius_mm"])
            patterns = wp_cfg.get("patterns")
            if isinstance(patterns, Mapping):
                values = [
                    float(cfg["wafer_radius_mm"])
                    for cfg in patterns.values()
                    if isinstance(cfg, Mapping) and cfg.get("wafer_radius_mm") is not None
                ]
                if values:
                    return max(values)
    values = [float(p["r_mm"]) for p in particles if p.get("r_mm") is not None]
    return max(values) if values else None


def _compute_label_stats(
    particles: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    taxonomy: Mapping[str, dict[str, Any]],
    r_edges: list[float],
    theta_edges: list[float],
    quantiles: list[float],
    qc_cfg: Mapping[str, Any],
    wafer_radius_mm: float | None,
    spatial_cfg: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, dict[str, list[float]]] = {}
    coords_by_label_sample: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for particle in particles:
        label = str(particle.get("label"))
        entry = grouped.setdefault(label, {"r": [], "theta": [], "size": []})
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        entry["r"].append(r_mm)
        entry["theta"].append(theta_rad)
        entry["size"].append(float(particle["size_um"]))
        sample_id = particle.get("sample_id")
        if sample_id is not None:
            x_mm = particle.get("x_mm")
            y_mm = particle.get("y_mm")
            if x_mm is None or y_mm is None:
                x_mm, y_mm = polar_to_cartesian_mm(r_mm, theta_rad)
            coords_by_label_sample.setdefault(label, {}).setdefault(str(sample_id), []).append(
                (float(x_mm), float(y_mm))
            )

    sample_counts: dict[str, list[int]] = {}
    for sample in samples:
        label = str(sample.get("label"))
        counts = sample_counts.setdefault(label, [])
        counts.append(int(sample["n_particles"]))

    labels = sorted(set(taxonomy.keys()) | set(grouped.keys()) | set(sample_counts.keys()))
    label_stats: dict[str, Any] = {}
    label_rows: list[dict[str, Any]] = []
    total_particles = len(particles)
    total_samples = len(samples)
    violations_total = 0

    for label in labels:
        values = grouped.get(label, {"r": [], "theta": [], "size": []})
        r_values = values["r"]
        theta_values = values["theta"]
        size_values = values["size"]
        n_particles = len(r_values)
        n_samples = len(sample_counts.get(label, []))
        n_particles_stats = compute_size_stats(sample_counts.get(label, []), quantiles=quantiles)
        r_stats = compute_size_stats(r_values, quantiles=quantiles)
        size_stats = compute_size_stats(size_values, quantiles=quantiles)
        theta_stats = _compute_circular_stats(theta_values)
        hist_r, r_out = _compute_hist(r_values, r_edges)
        hist_theta, theta_out = _compute_hist(theta_values, theta_edges)
        theta_coverage = _coverage(hist_theta)
        spatial_stats = _compute_spatial_stats(
            coords_by_label_sample.get(label, {}),
            sample_counts.get(label, []),
            quantiles,
            spatial_cfg,
            wafer_radius_mm,
            n_particles,
        )

        meta = taxonomy.get(label, {})
        rule_checks, violations = _evaluate_rules(
            label=label,
            category=meta.get("category"),
            params=meta.get("params", {}),
            expected_rules=meta.get("expected_rules", []),
            r_stats=r_stats,
            theta_stats=theta_stats,
            theta_coverage=theta_coverage,
            spatial_stats=spatial_stats,
            wafer_radius_mm=wafer_radius_mm,
            rules_cfg=_read_mapping(qc_cfg.get("rules"), "wafer_particles.qc.rules"),
        )
        violations_total += len(violations)

        label_stats[label] = {
            "category": meta.get("category"),
            "expected_rules": meta.get("expected_rules", []),
            "n_samples": n_samples,
            "n_particles": n_particles,
            "n_particles_stats": n_particles_stats,
            "size_stats": size_stats,
            "r_stats": r_stats,
            "theta_stats": {
                **theta_stats,
                "coverage": theta_coverage,
            },
            "spatial": spatial_stats,
            "hist_r": {"counts": hist_r, "out_of_range": r_out},
            "hist_theta": {"counts": hist_theta, "out_of_range": theta_out},
            "rule_checks": rule_checks,
        }

        label_rows.append(
            {
                "label": label,
                "category": meta.get("category") or "",
                "n_samples": n_samples,
                "n_particles": n_particles,
                "n_particles_mean": n_particles_stats.get("mean"),
                "n_particles_std": n_particles_stats.get("std"),
                "size_mean": size_stats.get("mean"),
                "size_std": size_stats.get("std"),
                "r_mean": r_stats.get("mean"),
                "r_std": r_stats.get("std"),
                "theta_mean": theta_stats.get("mean"),
                "theta_std": theta_stats.get("std"),
                "theta_coverage": theta_coverage,
                "rule_violations": ";".join(violations),
            }
        )

    summary = {
        "labels": len(labels),
        "total_particles": total_particles,
        "total_samples": total_samples,
        "rule_violations": violations_total,
    }
    return label_stats, label_rows, summary


def _compute_hist(values: list[float], edges: list[float]) -> tuple[list[int], int]:
    counts = [0 for _ in range(len(edges) - 1)]
    out_of_range = 0
    if not values:
        return counts, out_of_range
    for value in values:
        if value < edges[0] or value > edges[-1]:
            out_of_range += 1
            continue
        if value == edges[-1]:
            counts[-1] += 1
            continue
        idx = _bisect_right(edges, value) - 1
        if idx < 0 or idx >= len(counts):
            out_of_range += 1
            continue
        counts[idx] += 1
    return counts, out_of_range


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


def _coverage(counts: list[int]) -> float | None:
    if not counts:
        return None
    non_zero = sum(1 for count in counts if count > 0)
    return non_zero / len(counts)


def _compute_circular_stats(values: list[float]) -> dict[str, Any]:
    count = len(values)
    if count == 0:
        return {"count": 0, "mean": None, "std": None, "r": None}
    sin_sum = sum(sin(value) for value in values)
    cos_sum = sum(cos(value) for value in values)
    mean_angle = atan2(sin_sum, cos_sum) % tau
    r = sqrt(sin_sum * sin_sum + cos_sum * cos_sum) / count
    if r <= 0:
        circ_std = None
    else:
        circ_std = sqrt(-2.0 * log(r))
    return {"count": count, "mean": mean_angle, "std": circ_std, "r": r}


def _resolve_grid_bins(cfg: Mapping[str, Any]) -> int:
    grid_bins = cfg.get("grid_bins", 12) if cfg else 12
    grid_bins = int(grid_bins)
    if grid_bins <= 0:
        raise ValueError("spatial.grid_bins must be positive")
    return grid_bins


def _compute_spatial_stats(
    sample_points: Mapping[str, list[tuple[float, float]]],
    sample_counts: list[int],
    quantiles: list[float],
    spatial_cfg: Mapping[str, Any],
    wafer_radius_mm: float | None,
    n_particles: int,
) -> dict[str, Any]:
    nn_distances = _nearest_neighbor_distances(sample_points)
    nn_stats = compute_size_stats(nn_distances, quantiles=quantiles)

    nn_expected = None
    nn_ratio = None
    n_samples = len(sample_counts)
    if wafer_radius_mm is not None and wafer_radius_mm > 0 and n_samples > 0 and n_particles > 0:
        area = pi * wafer_radius_mm * wafer_radius_mm
        mean_count = n_particles / n_samples
        if area > 0 and mean_count > 0:
            nn_expected = 1.0 / (2.0 * sqrt(mean_count / area))
    if nn_stats.get("mean") is not None and nn_expected is not None:
        nn_ratio = float(nn_stats["mean"]) / nn_expected

    grid_bins = _resolve_grid_bins(spatial_cfg)
    grid_counts, grid_cells = _grid_cell_counts(sample_points, sample_counts, wafer_radius_mm, grid_bins)
    grid_stats = compute_size_stats(grid_counts, quantiles=quantiles)
    grid_dispersion = None
    if grid_stats.get("mean") not in (None, 0) and grid_stats.get("std") is not None:
        grid_dispersion = (float(grid_stats["std"]) ** 2) / float(grid_stats["mean"])

    return {
        "nn_stats": nn_stats,
        "nn_mean_expected": nn_expected,
        "nn_mean_ratio": nn_ratio,
        "grid_bins": grid_bins,
        "grid_cells": grid_cells,
        "grid_counts": grid_stats,
        "grid_dispersion": grid_dispersion,
    }


def _nearest_neighbor_distances(
    sample_points: Mapping[str, list[tuple[float, float]]],
) -> list[float]:
    distances: list[float] = []
    for points in sample_points.values():
        if len(points) < 2:
            continue
        for idx, (x_i, y_i) in enumerate(points):
            min_dist = None
            for jdx, (x_j, y_j) in enumerate(points):
                if idx == jdx:
                    continue
                dx = x_i - x_j
                dy = y_i - y_j
                dist = sqrt(dx * dx + dy * dy)
                if min_dist is None or dist < min_dist:
                    min_dist = dist
            if min_dist is not None:
                distances.append(min_dist)
    return distances


def _grid_cell_counts(
    sample_points: Mapping[str, list[tuple[float, float]]],
    sample_counts: list[int],
    wafer_radius_mm: float | None,
    grid_bins: int,
) -> tuple[list[int], int]:
    if wafer_radius_mm is None or grid_bins <= 0:
        return [], 0
    cell_size = (2.0 * wafer_radius_mm) / grid_bins
    radius_sq = wafer_radius_mm * wafer_radius_mm
    active_cells: list[tuple[int, int]] = []
    cell_index: dict[tuple[int, int], int] = {}
    for ix in range(grid_bins):
        cx = -wafer_radius_mm + (ix + 0.5) * cell_size
        for iy in range(grid_bins):
            cy = -wafer_radius_mm + (iy + 0.5) * cell_size
            if cx * cx + cy * cy > radius_sq:
                continue
            key = (ix, iy)
            cell_index[key] = len(active_cells)
            active_cells.append(key)
    if not active_cells:
        return [], 0

    counts_all: list[int] = []
    for points in sample_points.values():
        counts = [0] * len(active_cells)
        for x_mm, y_mm in points:
            ix = int((x_mm + wafer_radius_mm) / cell_size)
            iy = int((y_mm + wafer_radius_mm) / cell_size)
            if ix >= grid_bins:
                ix = grid_bins - 1
            if iy >= grid_bins:
                iy = grid_bins - 1
            idx = cell_index.get((ix, iy))
            if idx is None:
                continue
            counts[idx] += 1
        counts_all.extend(counts)

    empty_samples = sum(1 for count in sample_counts if int(count) <= 0)
    if empty_samples > 0:
        counts_all.extend([0] * len(active_cells) * empty_samples)
    return counts_all, len(active_cells)


def _evaluate_rules(
    *,
    label: str,
    category: Any,
    params: Mapping[str, Any],
    expected_rules: list[Any],
    r_stats: Mapping[str, Any],
    theta_stats: Mapping[str, Any],
    theta_coverage: float | None,
    spatial_stats: Mapping[str, Any],
    wafer_radius_mm: float | None,
    rules_cfg: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    checks: list[dict[str, Any]] = []
    violations: list[str] = []
    category_name = str(category) if category else "unknown"
    if category_name == "ring":
        checks.extend(
            _rule_ring(r_stats, theta_coverage, wafer_radius_mm, rules_cfg.get("ring", {}))
        )
    elif category_name == "sector":
        checks.extend(
            _rule_sector(
                theta_stats,
                theta_coverage,
                params,
                rules_cfg.get("sector", {}),
            )
        )
    elif category_name == "line":
        checks.extend(_rule_line(theta_coverage, rules_cfg.get("line", {})))
    elif category_name == "hotspot":
        checks.extend(_rule_hotspot(r_stats, wafer_radius_mm, params, rules_cfg.get("hotspot", {})))
    elif category_name == "inhom_poisson":
        checks.extend(_rule_inhom_poisson(spatial_stats, rules_cfg.get("inhom_poisson", {})))
    elif category_name == "cluster":
        checks.extend(_rule_cluster(spatial_stats, rules_cfg.get("cluster", {})))
    elif category_name == "cox":
        checks.extend(_rule_cox(spatial_stats, rules_cfg.get("cox", {})))

    for check in checks:
        if check.get("ok") is False:
            violations.append(check["name"])

    return (
        {
            "category": category_name,
            "expected_rules": expected_rules,
            "checks": checks,
        },
        violations,
    )


def _rule_ring(
    r_stats: Mapping[str, Any],
    theta_coverage: float | None,
    wafer_radius_mm: float | None,
    cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    max_r_std_ratio = cfg.get("max_r_std_ratio")
    if max_r_std_ratio is not None:
        checks.append(
            _ratio_rule(
                "ring.r_std_ratio",
                r_stats.get("std"),
                wafer_radius_mm,
                float(max_r_std_ratio),
                "max",
            )
        )
    min_theta_coverage = cfg.get("min_theta_coverage")
    if min_theta_coverage is not None:
        checks.append(
            _coverage_rule(
                "ring.theta_coverage",
                theta_coverage,
                float(min_theta_coverage),
                "min",
            )
        )
    return checks


def _rule_sector(
    theta_stats: Mapping[str, Any],
    theta_coverage: float | None,
    params: Mapping[str, Any],
    cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    max_theta_coverage = cfg.get("max_theta_coverage")
    if max_theta_coverage is not None:
        checks.append(
            _coverage_rule(
                "sector.theta_coverage",
                theta_coverage,
                float(max_theta_coverage),
                "max",
            )
        )
    expected_center = _resolve_expected_center(params)
    max_center_offset = cfg.get("max_center_offset_rad")
    if expected_center is not None and max_center_offset is not None:
        mean_angle = theta_stats.get("mean")
        if mean_angle is None:
            checks.append(_skipped_rule("sector.center_offset", "missing theta mean"))
        else:
            offset = _angular_distance(float(mean_angle), expected_center)
            ok = offset <= float(max_center_offset)
            checks.append(
                {
                    "name": "sector.center_offset",
                    "ok": ok,
                    "value": offset,
                    "threshold": {"max": float(max_center_offset)},
                    "status": "checked",
                }
            )
    return checks


def _rule_line(theta_coverage: float | None, cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    max_theta_coverage = cfg.get("max_theta_coverage")
    if max_theta_coverage is not None:
        checks.append(
            _coverage_rule(
                "line.theta_coverage",
                theta_coverage,
                float(max_theta_coverage),
                "max",
            )
        )
    return checks


def _rule_hotspot(
    r_stats: Mapping[str, Any],
    wafer_radius_mm: float | None,
    params: Mapping[str, Any],
    cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    mode = str(params.get("mode", "")).lower()
    r_mean = r_stats.get("mean")
    if wafer_radius_mm is None or r_mean is None:
        return checks
    r_mean_ratio = float(r_mean) / wafer_radius_mm
    if mode == "center":
        max_ratio = cfg.get("center_max_r_mean_ratio")
        if max_ratio is not None:
            checks.append(
                _ratio_rule("hotspot.center_r_mean_ratio", r_mean, wafer_radius_mm, float(max_ratio), "max")
            )
    elif mode == "edge":
        min_ratio = cfg.get("edge_min_r_mean_ratio")
        if min_ratio is not None:
            checks.append(
                _ratio_rule("hotspot.edge_r_mean_ratio", r_mean, wafer_radius_mm, float(min_ratio), "min")
            )
    else:
        if mode:
            checks.append(_skipped_rule("hotspot.mode", f"unsupported mode: {mode}"))
    return checks


def _rule_inhom_poisson(
    spatial_stats: Mapping[str, Any],
    cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    min_dispersion = cfg.get("min_grid_dispersion")
    if min_dispersion is not None:
        checks.append(
            _threshold_rule(
                "inhom_poisson.grid_dispersion",
                spatial_stats.get("grid_dispersion"),
                float(min_dispersion),
                "min",
            )
        )
    return checks


def _rule_cluster(
    spatial_stats: Mapping[str, Any],
    cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    min_dispersion = cfg.get("min_grid_dispersion")
    if min_dispersion is not None:
        checks.append(
            _threshold_rule(
                "cluster.grid_dispersion",
                spatial_stats.get("grid_dispersion"),
                float(min_dispersion),
                "min",
            )
        )
    max_nn_ratio = cfg.get("max_nn_mean_ratio")
    if max_nn_ratio is not None:
        checks.append(
            _threshold_rule(
                "cluster.nn_mean_ratio",
                spatial_stats.get("nn_mean_ratio"),
                float(max_nn_ratio),
                "max",
            )
        )
    return checks


def _rule_cox(
    spatial_stats: Mapping[str, Any],
    cfg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    min_dispersion = cfg.get("min_grid_dispersion")
    if min_dispersion is not None:
        checks.append(
            _threshold_rule(
                "cox.grid_dispersion",
                spatial_stats.get("grid_dispersion"),
                float(min_dispersion),
                "min",
            )
        )
    return checks


def _ratio_rule(
    name: str,
    value: Any,
    denom: float | None,
    threshold: float,
    mode: str,
) -> dict[str, Any]:
    if value is None or denom in (None, 0.0):
        return _skipped_rule(name, "missing ratio inputs")
    ratio = float(value) / float(denom)
    if mode == "min":
        ok = ratio >= threshold
        bound = {"min": threshold}
    else:
        ok = ratio <= threshold
        bound = {"max": threshold}
    return {"name": name, "ok": ok, "value": ratio, "threshold": bound, "status": "checked"}


def _coverage_rule(name: str, value: float | None, threshold: float, mode: str) -> dict[str, Any]:
    if value is None:
        return _skipped_rule(name, "missing coverage")
    if mode == "min":
        ok = value >= threshold
        bound = {"min": threshold}
    else:
        ok = value <= threshold
        bound = {"max": threshold}
    return {"name": name, "ok": ok, "value": value, "threshold": bound, "status": "checked"}


def _threshold_rule(name: str, value: float | None, threshold: float, mode: str) -> dict[str, Any]:
    if value is None:
        return _skipped_rule(name, "missing value")
    if mode == "min":
        ok = value >= threshold
        bound = {"min": threshold}
    else:
        ok = value <= threshold
        bound = {"max": threshold}
    return {"name": name, "ok": ok, "value": value, "threshold": bound, "status": "checked"}


def _skipped_rule(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "ok": None, "value": None, "threshold": None, "status": "skipped", "reason": reason}


def _resolve_expected_center(params: Mapping[str, Any]) -> float | None:
    if "angle_center_rad" in params:
        return float(params["angle_center_rad"]) % tau
    if "angle_center_deg" in params:
        return float(params["angle_center_deg"]) * tau / 360.0
    side = str(params.get("side", "")).lower()
    if side in _SIDE_TO_CENTER_RAD:
        return _SIDE_TO_CENTER_RAD[side]
    return None


def _angular_distance(a: float, b: float) -> float:
    diff = abs(a - b) % tau
    if diff > tau / 2.0:
        diff = tau - diff
    return diff


def _write_label_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "label",
        "category",
        "n_samples",
        "n_particles",
        "n_particles_mean",
        "n_particles_std",
        "size_mean",
        "size_std",
        "r_mean",
        "r_std",
        "theta_mean",
        "theta_std",
        "theta_coverage",
        "rule_violations",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_format_row(row, fieldnames))


def _format_row(row: Mapping[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    formatted: dict[str, Any] = {}
    for key in fieldnames:
        value = row.get(key)
        if value is None:
            formatted[key] = ""
        else:
            formatted[key] = value
    return formatted


def _input_payload(paths: InputPaths) -> dict[str, Any]:
    return {
        "run_dir": str(paths.run_dir) if paths.run_dir else None,
        "manifest_path": str(paths.manifest_path) if paths.manifest_path else None,
        "particles_path": str(paths.particles_path),
        "samples_path": str(paths.samples_path),
    }


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
