from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path
from typing import Any, Iterable, Mapping

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    polar_to_cartesian_mm,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.viz import plot_histograms, plot_label_samples
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import input_payload, read_table, resolve_input_paths

@register_process("wafer_particles.process.viz")
class VizProcess(BaseProcess):
    name = "wafer_particles.process.viz"

    def run(self, writer) -> None:
        writer.log("viz start")
        _ensure_mpl_config_dir(writer.repo_root)
        viz_cfg = _resolve_viz_cfg(self.cfg)
        input_cfg = _read_mapping(viz_cfg.get("input"), "wafer_particles.viz.input")
        paths = resolve_input_paths(input_cfg, repo_root=writer.repo_root)

        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        if not particles:
            raise ValueError("particles table is empty")
        if not samples:
            raise ValueError("samples table is empty")
        validate_particles_table(particles)
        validate_samples_table(samples)

        _ensure_cartesian(particles)

        seed = int(self.cfg.get("seed"))
        samples_per_label = _coerce_positive_int(viz_cfg.get("samples_per_label"), "viz.samples_per_label")
        max_labels = _coerce_optional_positive_int(viz_cfg.get("max_labels"), "viz.max_labels")
        selection = _select_samples_by_label(
            samples,
            samples_per_label=samples_per_label,
            max_labels=max_labels,
            rng=random.Random(_derive_seed(seed, 0, "viz_sample_selection")),
        )
        if not selection:
            raise ValueError("no label samples available for plotting")

        scatter_cfg = _read_mapping(viz_cfg.get("scatter"), "wafer_particles.viz.scatter", required=False)
        point_size = float(scatter_cfg.get("point_size", 6.0))
        alpha = float(scatter_cfg.get("alpha", 0.7))
        max_points = _coerce_optional_positive_int(scatter_cfg.get("max_points"), "viz.scatter.max_points")

        hist_cfg = _read_mapping(viz_cfg.get("hist"), "wafer_particles.viz.hist", required=False)
        r_values = [float(p["r_mm"]) for p in particles if p.get("r_mm") is not None]
        theta_values = [float(p["theta_rad"]) for p in particles if p.get("theta_rad") is not None]
        size_values = [float(p["size_um"]) for p in particles if p.get("size_um") is not None]
        r_edges = _resolve_edges(hist_cfg.get("r"), "hist.r", values=r_values, default_count=30)
        theta_edges = _resolve_edges(hist_cfg.get("theta"), "hist.theta", values=theta_values, default_count=36)
        size_edges = _resolve_edges(hist_cfg.get("size"), "hist.size", values=size_values, default_count=30)

        wafer_radius_mm = _resolve_wafer_radius_mm(viz_cfg, paths.input_config, particles)
        component_key = "component" if any(particle.get("component") is not None for particle in particles) else None

        plots_dir = writer.run_dir / "plots"
        plot_files: list[str] = []
        plot_files.extend(
            plot_label_samples(
                particles,
                selection,
                plots_dir,
                max_points=max_points,
                point_size=point_size,
                alpha=alpha,
                wafer_radius_mm=wafer_radius_mm,
                component_key=component_key,
            )
        )
        plot_files.append(
            plot_histograms(
                particles,
                plots_dir / "histograms.png",
                r_edges=r_edges,
                theta_edges=theta_edges,
                size_edges=size_edges,
            )
        )

        metrics = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": input_payload(paths),
            "n_particles": len(particles),
            "n_samples": len(samples),
            "label_distribution": _label_distribution(samples),
            "sample_selection": selection,
            "hist_bins": {
                "r_edges": r_edges,
                "theta_edges": theta_edges,
                "size_edges": size_edges,
            },
            "plots": plot_files,
        }
        writer.write_json("metrics/viz_summary.json", metrics)

        _append_readme(writer.run_dir / "README.md")
        writer.log("viz complete")


def _ensure_mpl_config_dir(repo_root: Path) -> Path:
    env_value = os.environ.get("MPLCONFIGDIR")
    if env_value:
        return Path(env_value)
    cfg_dir = repo_root / ".mplconfig"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cfg_dir)
    return cfg_dir

def _resolve_viz_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    viz_cfg = wp_cfg.get("viz")
    if not isinstance(viz_cfg, Mapping):
        raise ValueError("wafer_particles.viz config is required")
    return dict(viz_cfg)

def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)

def _ensure_cartesian(particles: list[dict[str, Any]]) -> None:
    for particle in particles:
        if particle.get("x_mm") is not None and particle.get("y_mm") is not None:
            continue
        r_mm = float(particle["r_mm"])
        theta_rad = float(particle["theta_rad"])
        x_mm, y_mm = polar_to_cartesian_mm(r_mm, theta_rad)
        particle["x_mm"] = x_mm
        particle["y_mm"] = y_mm


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
    parsed = _coerce_positive_int(value, name)
    return parsed


def _select_samples_by_label(
    samples: list[dict[str, Any]],
    *,
    samples_per_label: int,
    max_labels: int | None,
    rng: random.Random,
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for sample in samples:
        label = sample.get("label")
        sample_id = sample.get("sample_id")
        if label is None or sample_id is None:
            continue
        grouped.setdefault(str(label), []).append(str(sample_id))

    labels = sorted(grouped.keys())
    if max_labels is not None:
        labels = labels[:max_labels]

    selected: dict[str, list[str]] = {}
    for label in labels:
        sample_ids = sorted(set(grouped[label]))
        if sample_ids:
            rng.shuffle(sample_ids)
            selected[label] = sample_ids[:samples_per_label]
    return selected


def _resolve_edges(
    cfg: Any,
    name: str,
    *,
    values: Iterable[float] | None,
    default_count: int,
) -> list[float]:
    if cfg is None:
        return _edges_from_values(values, name, default_count)
    if isinstance(cfg, Mapping) and "edges" in cfg:
        edges = [float(value) for value in cfg["edges"]]
    elif isinstance(cfg, Mapping):
        start = cfg.get("start")
        stop = cfg.get("stop")
        count = cfg.get("count", default_count)
        if start is None or stop is None:
            return _edges_from_values(values, name, int(count))
        edges = _linspace(float(start), float(stop), int(count))
    else:
        raise ValueError(f"{name} must be a mapping")
    _validate_edges(edges, name)
    return edges


def _edges_from_values(values: Iterable[float] | None, name: str, count: int) -> list[float]:
    if values is None:
        raise ValueError(f"{name} requires edges or values")
    values_list = [float(value) for value in values]
    if not values_list:
        raise ValueError(f"{name} values are empty")
    start = min(values_list)
    stop = max(values_list)
    if start == stop:
        stop = start + 1.0
    edges = _linspace(start, stop, count)
    _validate_edges(edges, name)
    return edges


def _validate_edges(edges: list[float], name: str) -> None:
    if len(edges) < 2:
        raise ValueError(f"{name} must have at least 2 edges")
    if any(edges[i] >= edges[i + 1] for i in range(len(edges) - 1)):
        raise ValueError(f"{name} edges must be strictly increasing")


def _linspace(start: float, stop: float, count: int) -> list[float]:
    if count <= 0:
        raise ValueError("count must be positive")
    step = (stop - start) / count
    return [start + step * idx for idx in range(count + 1)]


def _derive_seed(base_seed: int, offset: int, component: str) -> int:
    payload = f"{base_seed}:{offset}:{component}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(base_seed) + int(digest[:12], 16)


def _resolve_wafer_radius_mm(
    viz_cfg: Mapping[str, Any],
    input_cfg: Mapping[str, Any] | None,
    particles: list[Mapping[str, Any]],
) -> float | None:
    if viz_cfg.get("wafer_radius_mm") is not None:
        return float(viz_cfg["wafer_radius_mm"])
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


def _label_distribution(samples: list[dict[str, Any]]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for sample in samples:
        label = sample.get("label")
        if label is None:
            continue
        label = str(label)
        distribution[label] = distribution.get(label, 0) + 1
    return distribution


def _append_readme(path: Path) -> None:
    lines = [
        "",
        "## Viz Outputs",
        "- scatter_label_<label>.png: label-specific sample scatter plots",
        "- histograms.png: r/theta/size histograms (bins align with qc config)",
    ]
    path.write_text(path.read_text(encoding="utf-8") + "\n".join(lines) + "\n", encoding="utf-8")


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
