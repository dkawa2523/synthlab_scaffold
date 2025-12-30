from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    PARTICLES_SCHEMA,
    SCHEMA_VERSION,
    SAMPLES_SCHEMA,
    build_manifest,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.framework.artifacts import compute_config_hash
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import input_payload, read_table, resolve_input_paths


@register_process("wafer_particles.process.export")
class ExportProcess(BaseProcess):
    name = "wafer_particles.process.export"

    def run(self, writer) -> None:
        writer.log("export start")
        wp_cfg = _resolve_wafer_particles_cfg(self.cfg)
        export_cfg = _read_mapping(wp_cfg.get("export"), "wafer_particles.export")
        input_cfg = _read_mapping(export_cfg.get("input"), "wafer_particles.export.input")
        split_cfg = _read_mapping(export_cfg.get("split"), "wafer_particles.export.split")

        paths = resolve_input_paths(
            input_cfg,
            repo_root=writer.repo_root,
            default_process_name="wafer_particles.process.generate",
        )
        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        validate_particles_table(particles)
        validate_samples_table(samples)

        seed = _coerce_int(self.cfg.get("seed"), "seed")
        split_seed_offset = _coerce_int(split_cfg.get("seed_offset", 0), "wafer_particles.export.split.seed_offset")
        split_seed = _derive_seed(seed, split_seed_offset, "export_split")
        split_map, split_assignments = _assign_splits(samples, split_cfg, split_seed)

        sample_index_rows = _build_sample_index(samples, split_map)
        particle_index_rows = _build_particle_index(particles, split_map)

        io_cfg = _read_mapping(wp_cfg.get("io"), "wafer_particles.io")
        fmt_raw = str(io_cfg.get("format", "auto")).lower()
        fmt, auto_selected = _resolve_output_format(fmt_raw)
        if auto_selected:
            writer.log(f"io.format=auto resolved to {fmt}")
        csv_cfg = _read_mapping(io_cfg.get("csv"), "wafer_particles.io.csv", required=False)
        parquet_cfg = _read_mapping(io_cfg.get("parquet"), "wafer_particles.io.parquet", required=False)
        particles_path, samples_path, index_samples_path, index_particles_path = _data_paths(fmt)

        _write_table(
            writer.run_dir / particles_path,
            particles,
            fmt=fmt,
            csv_cfg=csv_cfg,
            parquet_cfg=parquet_cfg,
            columns=_columns_for_rows(particles, PARTICLES_SCHEMA),
        )
        _write_table(
            writer.run_dir / samples_path,
            samples,
            fmt=fmt,
            csv_cfg=csv_cfg,
            parquet_cfg=parquet_cfg,
            columns=_columns_for_rows(samples, SAMPLES_SCHEMA),
        )
        _write_table(
            writer.run_dir / index_samples_path,
            sample_index_rows,
            fmt=fmt,
            csv_cfg=csv_cfg,
            parquet_cfg=parquet_cfg,
            columns=_index_sample_columns(),
        )
        _write_table(
            writer.run_dir / index_particles_path,
            particle_index_rows,
            fmt=fmt,
            csv_cfg=csv_cfg,
            parquet_cfg=parquet_cfg,
            columns=_index_particle_columns(),
        )

        domain = _domain_name(self.cfg)
        schema_version = str(self.cfg.get("schema_version", SCHEMA_VERSION))
        dataset_id = _dataset_id(domain, schema_version, writer.config_hash)
        input_config_hash = compute_config_hash(paths.input_config) if isinstance(paths.input_config, dict) else None

        label_distribution = _label_distribution(samples)
        manifest = build_manifest(
            particles_path=particles_path,
            samples_path=samples_path,
            particles_rows=len(particles),
            samples_rows=len(samples),
            label_distribution=label_distribution,
            schema_version=schema_version,
            domain=domain,
        )
        manifest["dataset_id"] = dataset_id
        manifest["config_hash"] = writer.config_hash
        manifest["input_config_hash"] = input_config_hash
        manifest["input"] = input_payload(paths)
        manifest["files"]["index_samples"] = {"path": index_samples_path, "rows": len(sample_index_rows)}
        manifest["files"]["index_particles"] = {"path": index_particles_path, "rows": len(particle_index_rows)}
        split_stats = _summarize_splits(samples, particles, split_map, split_assignments)
        split_counts = _split_counts(split_stats)
        manifest["splits"] = {
            "path": "splits/splits.json",
            "ratios": _split_ratios(split_cfg),
            "summary": split_counts,
        }
        writer.write_json("manifest.json", manifest)

        splits_payload = {
            "dataset_id": dataset_id,
            "schema_version": schema_version,
            "domain": domain,
            "seed": seed,
            "seed_offset": split_seed_offset,
            "split": _split_config_payload(split_cfg),
            "splits": split_stats,
            "sample_ids": split_assignments,
        }
        writer.write_json("splits/splits.json", splits_payload)

        metrics = {
            "dataset_id": dataset_id,
            "schema_version": schema_version,
            "domain": domain,
            "input": input_payload(paths),
            "input_config_hash": input_config_hash,
            "split": _split_config_payload(split_cfg),
            "splits": split_stats,
            "label_distribution": label_distribution,
        }
        writer.write_json("metrics/export_summary.json", metrics)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=export\n",
            encoding="utf-8",
        )
        writer.log("export complete")


def _resolve_wafer_particles_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    return dict(wp_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _coerce_int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an int")


def _derive_seed(base_seed: int, offset: int, component: str) -> int:
    payload = f"{base_seed}:{offset}:{component}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(base_seed) + int(digest[:12], 16)


def _data_paths(fmt: str) -> tuple[str, str, str, str]:
    if fmt == "csv":
        return (
            "data/particles.csv",
            "data/samples.csv",
            "data/index_samples.csv",
            "data/index_particles.csv",
        )
    if fmt == "parquet":
        return (
            "data/particles.parquet",
            "data/samples.parquet",
            "data/index_samples.parquet",
            "data/index_particles.parquet",
        )
    raise ValueError(f"unsupported io.format: {fmt}")


def _resolve_output_format(fmt: str) -> tuple[str, bool]:
    if fmt != "auto":
        return fmt, False
    try:
        import pyarrow  # noqa: F401
    except Exception:
        return "csv", True
    return "parquet", True


def _split_ratios(split_cfg: Mapping[str, Any]) -> dict[str, float]:
    ratios = split_cfg.get("ratios") or {}
    if not isinstance(ratios, Mapping):
        raise ValueError("wafer_particles.export.split.ratios must be a mapping")
    if not ratios:
        raise ValueError("wafer_particles.export.split.ratios is empty")
    return {str(key): float(value) for key, value in ratios.items()}


def _split_config_payload(split_cfg: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mode": str(split_cfg.get("mode", "ratio")).lower(),
        "shuffle": bool(split_cfg.get("shuffle", True)),
        "ratios": _split_ratios(split_cfg),
    }


def _assign_splits(
    samples: Sequence[Mapping[str, Any]],
    split_cfg: Mapping[str, Any],
    seed: int,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    mode = str(split_cfg.get("mode", "ratio")).lower()
    if mode != "ratio":
        raise ValueError("wafer_particles.export.split.mode must be 'ratio'")
    ratios = _split_ratios(split_cfg)
    names = list(ratios.keys())
    weights = [float(ratios[name]) for name in names]

    sample_ids: list[str] = []
    for row in samples:
        sample_id = row.get("sample_id")
        if sample_id is None or sample_id == "":
            raise ValueError("sample_id must be set for all samples")
        sample_ids.append(str(sample_id))
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("sample_id values must be unique")
    ordered = sorted(sample_ids)

    if split_cfg.get("shuffle", True):
        rng = random.Random(seed)
        rng.shuffle(ordered)

    counts = _allocate_counts(len(ordered), weights)
    split_map: dict[str, str] = {}
    split_assignments: dict[str, list[str]] = {name: [] for name in names}
    cursor = 0
    for name, count in zip(names, counts):
        for _ in range(count):
            sample_id = ordered[cursor]
            cursor += 1
            split_map[sample_id] = name
            split_assignments[name].append(sample_id)
    if cursor != len(ordered):
        raise ValueError("split assignment mismatch")
    return split_map, split_assignments


def _allocate_counts(total: int, weights: Sequence[float]) -> list[int]:
    if total <= 0:
        return [0 for _ in weights]
    if not weights:
        return []
    if any(weight < 0 for weight in weights):
        raise ValueError("wafer_particles.export.split.ratios must be non-negative")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("wafer_particles.export.split.ratios must sum to > 0")
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


def _build_sample_index(
    samples: Sequence[Mapping[str, Any]],
    split_map: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in samples:
        sample_id = str(row.get("sample_id"))
        split = split_map.get(sample_id)
        if split is None:
            raise ValueError(f"missing split for sample_id: {sample_id}")
        rows.append(
            {
                "sample_id": sample_id,
                "split": split,
                "label": str(row.get("label")),
                "n_particles": int(row.get("n_particles")),
            }
        )
    return rows


def _build_particle_index(
    particles: Sequence[Mapping[str, Any]],
    split_map: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in particles:
        sample_id = str(row.get("sample_id"))
        split = split_map.get(sample_id)
        if split is None:
            raise ValueError(f"missing split for sample_id: {sample_id}")
        rows.append(
            {
                "sample_id": sample_id,
                "particle_id": int(row.get("particle_id")),
                "split": split,
                "label": str(row.get("label")),
            }
        )
    return rows


def _columns_for_rows(rows: Sequence[Mapping[str, Any]], schema) -> list[str]:
    preferred = [spec.name for spec in schema.required] + [spec.name for spec in schema.optional]
    keys: set[str] = set()
    for row in rows:
        keys.update(str(key) for key in row.keys())
    columns: list[str] = [name for name in preferred if name in keys]
    columns.extend(sorted(keys - set(columns)))
    if not columns:
        return list(preferred)
    return columns


def _index_sample_columns() -> list[str]:
    return ["sample_id", "split", "label", "n_particles"]


def _index_particle_columns() -> list[str]:
    return ["sample_id", "particle_id", "split", "label"]


def _label_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for row in rows:
        label = row.get("label")
        if label is None:
            continue
        key = str(label)
        dist[key] = dist.get(key, 0) + 1
    return dist


def _summarize_splits(
    samples: Sequence[Mapping[str, Any]],
    particles: Sequence[Mapping[str, Any]],
    split_map: Mapping[str, str],
    split_assignments: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for split_name, sample_ids in split_assignments.items():
        summary[split_name] = {
            "n_samples": 0,
            "n_particles": 0,
            "sample_label_distribution": {},
            "particle_label_distribution": {},
        }

    for row in samples:
        sample_id = str(row.get("sample_id"))
        split = split_map.get(sample_id)
        if split is None:
            raise ValueError(f"missing split for sample_id: {sample_id}")
        slot = summary[split]
        slot["n_samples"] += 1
        label = str(row.get("label"))
        label_dist = slot["sample_label_distribution"]
        label_dist[label] = label_dist.get(label, 0) + 1

    for row in particles:
        sample_id = str(row.get("sample_id"))
        split = split_map.get(sample_id)
        if split is None:
            raise ValueError(f"missing split for sample_id: {sample_id}")
        slot = summary[split]
        slot["n_particles"] += 1
        label = str(row.get("label"))
        label_dist = slot["particle_label_distribution"]
        label_dist[label] = label_dist.get(label, 0) + 1

    return summary


def _split_counts(split_stats: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for split_name, stats in split_stats.items():
        counts[split_name] = {
            "n_samples": int(stats.get("n_samples", 0)),
            "n_particles": int(stats.get("n_particles", 0)),
        }
    return counts


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


def _dataset_id(domain: str, schema_version: str, config_hash: str) -> str:
    return f"{domain}.{schema_version}.{config_hash}"


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
