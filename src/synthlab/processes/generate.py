from __future__ import annotations

import csv
import hashlib
import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    build_manifest,
    polar_to_cartesian_mm,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.generators.size_models.common import apply_size_model
from synthlab.domains.wafer_particles.metrics.size_stats import (
    compute_size_stats_by_label,
    compute_size_stats_from_particles,
)
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import get_pattern, register_process

import synthlab.domains.wafer_particles.generators  # noqa: F401


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
        patterns_cfg = _resolve_patterns_cfg(wp_cfg)
        labels_cfg = wp_cfg.get("labels")
        label_defs = _resolve_label_defs(labels_cfg, patterns_cfg)

        label_rng = random.Random(_derive_seed(seed, 0, "label_selection"))
        labels = _select_labels(n_samples, label_selection, label_defs, label_rng)

        sample_id_prefix = str(wp_cfg.get("sample_id_prefix", "sample"))
        include_xy = bool(wp_cfg.get("include_xy", True))
        source = wp_cfg.get("source")
        sample_ctx = _build_sample_ctx(wp_cfg)
        size_model_cfg = _resolve_size_model_cfg(wp_cfg)

        particles: list[dict[str, Any]] = []
        samples: list[dict[str, Any]] = []
        label_distribution: dict[str, int] = {}
        particle_label_distribution: dict[str, int] = {}

        for idx, label in enumerate(labels):
            seed_offset = idx
            sample_id = f"{sample_id_prefix}_{idx:06d}"
            pattern_cfg = deepcopy(label_defs[label])
            pattern_rng = random.Random(_derive_seed(seed, seed_offset, "pattern"))
            size_rng = random.Random(_derive_seed(seed, seed_offset, "size_model"))
            pattern_name = str(pattern_cfg.get("name", ""))
            generator = get_pattern(pattern_name)
            sample_particles = generator(pattern_cfg, pattern_rng, sample_ctx)

            for particle_id, particle in enumerate(sample_particles):
                particle["sample_id"] = sample_id
                particle["particle_id"] = particle_id
                particle["label"] = label
                if source is not None:
                    particle["source"] = str(source)
            apply_size_model(size_model_cfg, size_rng, sample_particles)
            if include_xy:
                _append_cartesian(sample_particles)

            n_particles = len(sample_particles)
            particles.extend(sample_particles)
            samples.append(
                {
                    "sample_id": sample_id,
                    "label": label,
                    "n_particles": n_particles,
                    "pattern_params": json.dumps(pattern_cfg, sort_keys=True, ensure_ascii=True),
                    "seed_offset": seed_offset,
                }
            )
            label_distribution[label] = label_distribution.get(label, 0) + 1
            particle_label_distribution[label] = particle_label_distribution.get(label, 0) + n_particles

        validate_particles_table(particles)
        validate_samples_table(samples)

        io_cfg = _read_mapping(wp_cfg.get("io"), "wafer_particles.io")
        fmt_raw = str(io_cfg.get("format", "auto")).lower()
        fmt, auto_selected = _resolve_output_format(fmt_raw)
        if auto_selected:
            writer.log(f"io.format=auto resolved to {fmt}")
        particles_path, samples_path = _data_paths(fmt)
        _write_table(
            writer.run_dir / particles_path,
            particles,
            fmt=fmt,
            csv_cfg=_read_mapping(io_cfg.get("csv"), "wafer_particles.io.csv", required=False),
            parquet_cfg=_read_mapping(io_cfg.get("parquet"), "wafer_particles.io.parquet", required=False),
            columns=_particle_columns(particles, include_xy=include_xy, include_source=source is not None),
        )
        _write_table(
            writer.run_dir / samples_path,
            samples,
            fmt=fmt,
            csv_cfg=_read_mapping(io_cfg.get("csv"), "wafer_particles.io.csv", required=False),
            parquet_cfg=_read_mapping(io_cfg.get("parquet"), "wafer_particles.io.parquet", required=False),
            columns=_sample_columns(),
        )

        domain = _domain_name(cfg)
        schema_version = cfg.get("schema_version", SCHEMA_VERSION)
        manifest = build_manifest(
            particles_path=particles_path,
            samples_path=samples_path,
            particles_rows=len(particles),
            samples_rows=len(samples),
            label_distribution=label_distribution,
            schema_version=str(schema_version),
            domain=str(domain),
        )
        writer.write_json("manifest.json", manifest)

        metrics = {
            "n_samples": n_samples,
            "n_particles": len(particles),
            "label_distribution": label_distribution,
            "particle_label_distribution": particle_label_distribution,
            "size_stats": compute_size_stats_from_particles(particles),
            "size_stats_by_label": compute_size_stats_by_label(particles),
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
    patterns = wp_cfg.get("patterns")
    if not isinstance(patterns, Mapping):
        raise ValueError("wafer_particles.patterns must be a mapping")
    resolved: dict[str, dict[str, Any]] = {}
    for label, cfg in patterns.items():
        if not isinstance(cfg, Mapping):
            raise ValueError(f"pattern config for {label} must be a mapping")
        resolved[str(label)] = deepcopy(dict(cfg))
    if not resolved:
        raise ValueError("wafer_particles.patterns is empty")
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
    if not ratios:
        labels = selection_cfg.get("labels")
        labels = [str(label) for label in labels] if isinstance(labels, list) and labels else available
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


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _particle_columns(
    particles: Sequence[Mapping[str, Any]],
    *,
    include_xy: bool,
    include_source: bool,
) -> list[str]:
    columns = ["sample_id", "particle_id", "r_mm", "theta_rad", "size_um", "label"]
    if include_xy:
        columns.extend(["x_mm", "y_mm"])
    has_component = any("component" in particle for particle in particles)
    if has_component:
        columns.append("component")
    if include_source:
        columns.append("source")
    return columns


def _sample_columns() -> list[str]:
    return ["sample_id", "label", "n_particles", "pattern_params", "seed_offset"]


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
