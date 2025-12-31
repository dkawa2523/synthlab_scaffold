from __future__ import annotations

import re
from math import ceil
from pathlib import Path
from typing import Any, Mapping, Sequence


def plot_label_samples(
    particles: Sequence[Mapping[str, Any]],
    sample_ids_by_label: Mapping[str, Sequence[str]],
    out_dir: Path,
    *,
    max_points: int | None,
    point_size: float,
    alpha: float,
    wafer_radius_mm: float | None,
    component_key: str | None = None,
) -> list[str]:
    plt = _get_pyplot()
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_id_set = {sample_id for ids in sample_ids_by_label.values() for sample_id in ids}
    particles_by_sample = _collect_particles_by_sample(particles, sample_id_set)
    component_palette = _resolve_component_palette(particles_by_sample, component_key)
    if component_key and not component_palette:
        component_key = None

    outputs: list[str] = []
    for label, sample_ids in sample_ids_by_label.items():
        if not sample_ids:
            continue
        ncols = min(3, len(sample_ids))
        nrows = ceil(len(sample_ids) / ncols)
        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 4 * nrows), squeeze=False)
        flat_axes = axes.ravel().tolist()
        for idx, sample_id in enumerate(sample_ids):
            ax = flat_axes[idx]
            sample_particles = particles_by_sample.get(sample_id, [])
            if max_points is not None and max_points > 0:
                sample_particles = list(_limit_points(sample_particles, max_points))
            if component_key:
                grouped = _group_by_component(sample_particles, component_key)
                for component, group in grouped.items():
                    xs, ys = _extract_xy(group, max_points=None)
                    if not xs:
                        continue
                    label_text = "unknown" if component is None else str(component)
                    color = component_palette.get(label_text, "#4C72B0")
                    ax.scatter(xs, ys, s=point_size, alpha=alpha, color=color, label=label_text)
                if len(grouped) > 1:
                    ax.legend(loc="upper right", fontsize="small")
            else:
                xs, ys = _extract_xy(sample_particles, max_points=None)
                ax.scatter(xs, ys, s=point_size, alpha=alpha)
            if wafer_radius_mm is not None:
                ax.set_xlim(-wafer_radius_mm, wafer_radius_mm)
                ax.set_ylim(-wafer_radius_mm, wafer_radius_mm)
            ax.set_aspect("equal", "box")
            ax.set_title(sample_id)
            ax.set_xlabel("x_mm")
            ax.set_ylabel("y_mm")
        for ax in flat_axes[len(sample_ids) :]:
            ax.set_visible(False)
        fig.suptitle(f"label: {label}")
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        filename = f"scatter_label_{_safe_label(label)}.png"
        fig.savefig(out_dir / filename, dpi=150)
        plt.close(fig)
        outputs.append(filename)
    return outputs


def plot_histograms(
    particles: Sequence[Mapping[str, Any]],
    out_path: Path,
    *,
    r_edges: Sequence[float],
    theta_edges: Sequence[float],
    size_edges: Sequence[float],
) -> str:
    plt = _get_pyplot()
    r_values = [float(p["r_mm"]) for p in particles if p.get("r_mm") is not None]
    theta_values = [float(p["theta_rad"]) for p in particles if p.get("theta_rad") is not None]
    size_values = [float(p["size_um"]) for p in particles if p.get("size_um") is not None]

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    axes[0].hist(r_values, bins=r_edges, color="#4C72B0", edgecolor="black")
    axes[0].set_title("r_mm")
    axes[0].set_xlabel("r_mm")
    axes[0].set_ylabel("count")

    axes[1].hist(theta_values, bins=theta_edges, color="#55A868", edgecolor="black")
    axes[1].set_title("theta_rad")
    axes[1].set_xlabel("theta_rad")
    axes[1].set_ylabel("count")

    axes[2].hist(size_values, bins=size_edges, color="#C44E52", edgecolor="black")
    axes[2].set_title("size_um")
    axes[2].set_xlabel("size_um")
    axes[2].set_ylabel("count")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path.name


def _collect_particles_by_sample(
    particles: Sequence[Mapping[str, Any]],
    sample_ids: set[str],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {sample_id: [] for sample_id in sample_ids}
    for particle in particles:
        sample_id = particle.get("sample_id")
        if sample_id in grouped:
            grouped[str(sample_id)].append(particle)
    return grouped


def _extract_xy(
    particles: Sequence[Mapping[str, Any]],
    *,
    max_points: int | None,
) -> tuple[list[float], list[float]]:
    if max_points is not None and max_points > 0:
        particles = _limit_points(particles, max_points)
    xs: list[float] = []
    ys: list[float] = []
    for particle in particles:
        if particle.get("x_mm") is None or particle.get("y_mm") is None:
            continue
        xs.append(float(particle["x_mm"]))
        ys.append(float(particle["y_mm"]))
    return xs, ys


def _limit_points(
    particles: Sequence[Mapping[str, Any]],
    max_points: int,
) -> Sequence[Mapping[str, Any]]:
    if len(particles) <= max_points:
        return particles
    ordered = sorted(particles, key=lambda row: row.get("particle_id", 0))
    return ordered[:max_points]


def _group_by_component(
    particles: Sequence[Mapping[str, Any]],
    component_key: str,
) -> dict[str | None, list[Mapping[str, Any]]]:
    grouped: dict[str | None, list[Mapping[str, Any]]] = {}
    for particle in particles:
        component = particle.get(component_key)
        key = None if component is None else str(component)
        grouped.setdefault(key, []).append(particle)
    return grouped


def _resolve_component_palette(
    particles_by_sample: Mapping[str, Sequence[Mapping[str, Any]]],
    component_key: str | None,
) -> dict[str, str]:
    if not component_key:
        return {}
    components: list[str] = []
    seen: set[str] = set()
    has_unknown = False
    for particles in particles_by_sample.values():
        for particle in particles:
            component = particle.get(component_key)
            if component is None:
                has_unknown = True
                continue
            component = str(component)
            if component in seen:
                continue
            seen.add(component)
            components.append(component)
    if has_unknown:
        components.append("unknown")
    palette = _COMPONENT_COLORS
    return {component: palette[idx % len(palette)] for idx, component in enumerate(sorted(components))}


def _safe_label(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    return safe.lower() or "label"


def _get_pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError("matplotlib is required for viz process") from exc
    return plt


_COMPONENT_COLORS = [
    "#4C72B0",
    "#55A868",
    "#C44E52",
    "#8172B2",
    "#CCB974",
    "#64B5CD",
]
