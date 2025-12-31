from __future__ import annotations

import csv
import json
import hashlib
import random
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    PARTICLES_SCHEMA,
    SCHEMA_VERSION,
    SAMPLES_SCHEMA,
    build_manifest,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.labeling import (
    LabelingSpec,
    UNKNOWN_LABEL,
    normalize_label_list,
    serialize_label_lists,
)
from synthlab.framework.artifacts import compute_config_hash
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import (
    input_payload,
    read_table,
    resolve_input_paths,
    resolve_path,
)


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
        _serialize_sample_label_lists(samples)
        validate_particles_table(particles)
        validate_samples_table(samples)

        apply_labeling_spec = bool(export_cfg.get("apply_labeling_spec", False))
        labeling_cfg = _read_mapping(wp_cfg.get("labeling"), "wafer_particles.labeling", required=False)
        labeling_spec = None
        labeling_spec_hash = None
        if apply_labeling_spec:
            spec_path = _resolve_labeling_spec_path(export_cfg, labeling_cfg, writer.repo_root)
            writer.log(f"apply labeling spec={spec_path}")
            labeling_spec = LabelingSpec.load(spec_path)
            labeling_spec_hash = labeling_spec.hash()
            labeling_spec.apply_to_particles(particles)
            labeling_spec.apply_to_samples(samples)
            serialize_label_lists(samples, _label_list_columns(labeling_spec))
            _write_labeling_spec_meta(writer.run_dir / "meta", labeling_spec)

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
        config_hash = writer.config_hash
        input_config_hash = compute_config_hash(paths.input_config) if isinstance(paths.input_config, dict) else None
        taxonomy_cfg = _resolve_taxonomy_cfg(paths.input_config, self.cfg)
        taxonomy_version = _taxonomy_version(taxonomy_cfg)
        metric_set_version = _resolve_metric_set_version(paths.input_config, self.cfg)
        dataset_config_hash = _dataset_config_hash(
            seed=seed,
            split_cfg=split_cfg,
            split_seed_offset=split_seed_offset,
            input_config_hash=input_config_hash,
        )
        dataset_id = _dataset_id(
            schema_version=schema_version,
            taxonomy_version=taxonomy_version,
            config_hash=config_hash,
            labeling_spec_hash=labeling_spec_hash,
            metric_set_version=metric_set_version,
        )
        _update_export_meta(
            writer.run_dir / "meta" / "meta.json",
            dataset_id=dataset_id,
            labeling_spec_hash=labeling_spec_hash,
            metric_set_version=metric_set_version,
        )

        label_distribution = _label_distribution(samples)
        label_summary = _collect_label_summary(
            samples=samples,
            particles=particles,
            label_distribution=label_distribution,
            labeling_spec=labeling_spec,
        )
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
        manifest["config_hash"] = config_hash
        manifest["dataset_config_hash"] = dataset_config_hash
        manifest["input_config_hash"] = input_config_hash
        manifest["taxonomy_version"] = taxonomy_version
        if labeling_spec_hash:
            manifest["labeling_spec_hash"] = labeling_spec_hash
        if metric_set_version:
            manifest["metric_set_version"] = metric_set_version
        manifest["input"] = input_payload(paths)
        manifest_files = manifest["files"]
        manifest_files["index_samples"] = {"path": index_samples_path, "rows": len(sample_index_rows)}
        manifest_files["index_particles"] = {"path": index_particles_path, "rows": len(particle_index_rows)}
        manifest_files["taxonomy_snapshot"] = {"path": "taxonomy_snapshot.yaml"}
        manifest_files["dataset_card"] = {"path": "DATASET_CARD.md"}
        manifest_files["dataset_card_report"] = {"path": "reports/dataset_card.md"}
        manifest_files["checksums"] = {"path": "checksums.sha256"}
        split_stats = _summarize_splits(samples, particles, split_map, split_assignments)
        split_counts = _split_counts(split_stats)
        manifest["splits"] = {
            "path": "splits/splits.json",
            "ratios": _split_ratios(split_cfg),
            "summary": split_counts,
        }
        package_cfg = _read_mapping(export_cfg.get("package"), "wafer_particles.export.package", required=False)
        package_format = _package_format(package_cfg)
        package_rel_path = None
        if package_format != "none":
            package_rel_path = _package_path(dataset_id, package_format)
            manifest["package"] = {"format": package_format, "path": package_rel_path}
        writer.write_json("manifest.json", manifest)
        _write_yaml(writer.run_dir / "manifest.yaml", manifest)

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

        taxonomy_snapshot = _taxonomy_snapshot(taxonomy_cfg, domain=domain)
        _write_yaml(writer.run_dir / "taxonomy_snapshot.yaml", taxonomy_snapshot)
        dataset_card = _render_dataset_card(
            dataset_id=dataset_id,
            domain=domain,
            schema_version=schema_version,
            taxonomy_version=taxonomy_version,
            created_at=writer.created_at,
            config_hash=config_hash,
            dataset_config_hash=dataset_config_hash,
            input_config_hash=input_config_hash,
            labeling_spec_hash=labeling_spec_hash,
            metric_set_version=metric_set_version,
            label_summary=label_summary,
            particles_path=particles_path,
            samples_path=samples_path,
            index_samples_path=index_samples_path,
            index_particles_path=index_particles_path,
            split_counts=split_counts,
            split_ratios=_split_ratios(split_cfg),
        )
        (writer.run_dir / "DATASET_CARD.md").write_text(dataset_card, encoding="utf-8")
        report_path = writer.run_dir / "reports" / "dataset_card.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(dataset_card, encoding="utf-8")

        bundle_files = _bundle_files(
            writer.run_dir,
            extra_rel_paths=[
                "manifest.json",
                "manifest.yaml",
                "taxonomy_snapshot.yaml",
                "DATASET_CARD.md",
                "reports/dataset_card.md",
            ],
        )
        checksums_path = writer.run_dir / "checksums.sha256"
        _write_checksums(checksums_path, writer.run_dir, bundle_files)

        metrics = {
            "dataset_id": dataset_id,
            "schema_version": schema_version,
            "domain": domain,
            "input": input_payload(paths),
            "input_config_hash": input_config_hash,
            "labeling_spec_hash": labeling_spec_hash,
            "metric_set_version": metric_set_version,
            "split": _split_config_payload(split_cfg),
            "splits": split_stats,
            "label_distribution": label_distribution,
        }
        writer.write_json("metrics/export_summary.json", metrics)
        if package_rel_path is not None:
            package_files = _bundle_files(
                writer.run_dir,
                extra_rel_paths=[
                    "manifest.json",
                    "manifest.yaml",
                    "taxonomy_snapshot.yaml",
                    "DATASET_CARD.md",
                    "reports/dataset_card.md",
                    "checksums.sha256",
                ],
            )
            _write_package(
                writer.run_dir,
                package_rel_path,
                package_format,
                package_files,
            )
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


def _resolve_labeling_spec_path(
    export_cfg: Mapping[str, Any],
    labeling_cfg: Mapping[str, Any],
    repo_root: Path,
) -> Path:
    spec_path = export_cfg.get("labeling_spec_path") or labeling_cfg.get("spec_path")
    if not spec_path:
        raise ValueError(
            "wafer_particles.export.labeling_spec_path or wafer_particles.labeling.spec_path is required"
        )
    return resolve_path(spec_path, repo_root)


def _write_labeling_spec_meta(meta_dir: Path, spec: LabelingSpec) -> None:
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "labeling_spec.yaml").write_text(spec.to_yaml(), encoding="utf-8")
    (meta_dir / "labeling_spec_hash.txt").write_text(spec.hash() + "\n", encoding="utf-8")


def _update_export_meta(
    meta_path: Path,
    *,
    dataset_id: str,
    labeling_spec_hash: str | None,
    metric_set_version: str | None,
) -> None:
    if not meta_path.exists():
        return
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"meta.json must be a mapping: {meta_path}")
    payload["dataset_id"] = dataset_id
    if labeling_spec_hash:
        payload["labeling_spec_hash"] = labeling_spec_hash
    if metric_set_version:
        payload["metric_set_version"] = metric_set_version
    meta_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _label_list_columns(spec: LabelingSpec) -> list[str]:
    return [f"labels_{suffix}" for suffix in spec.layer_columns.values()]


def _label_list_columns_from_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    columns: set[str] = set()
    for row in rows:
        for key in row.keys():
            if isinstance(key, str) and key.startswith("labels_"):
                columns.add(key)
    return sorted(columns)


def _serialize_sample_label_lists(rows: Sequence[Mapping[str, Any]]) -> None:
    columns = _label_list_columns_from_rows(rows)
    if columns:
        serialize_label_lists(rows, columns)


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


def _collect_label_summary(
    *,
    samples: Sequence[Mapping[str, Any]],
    particles: Sequence[Mapping[str, Any]],
    label_distribution: Mapping[str, int],
    labeling_spec: LabelingSpec | None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "primary": dict(label_distribution),
        "fine_single": _count_fine_labels(samples),
        "fine_multi": None,
        "layers": {},
        "similarity_groups": [],
    }
    if _has_column(samples, "labels_fine"):
        summary["fine_multi"] = _count_list_values(samples, "labels_fine")
    if labeling_spec is not None:
        summary["layers"] = _summarize_layer_distributions(labeling_spec, particles, samples)
        summary["similarity_groups"] = _summarize_similarity_groups(labeling_spec, particles, samples)
    return summary


def _count_values(
    rows: Sequence[Mapping[str, Any]],
    column: str,
    *,
    empty_label: str | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(column)
        if value in (None, ""):
            if empty_label is None:
                continue
            key = empty_label
        else:
            key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_list_values(rows: Sequence[Mapping[str, Any]], column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        labels = normalize_label_list(row.get(column))
        for label in labels:
            key = str(label)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _count_fine_labels(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = row.get("label_fine")
        if label in (None, ""):
            label = row.get("label")
        key = UNKNOWN_LABEL if label in (None, "") else str(label)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _summarize_layer_distributions(
    spec: LabelingSpec,
    particles: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for layer_name, _mapping in spec.layers.items():
        suffix = spec.layer_columns[layer_name]
        entry: dict[str, Any] = {
            "layer_name": layer_name,
            "column_suffix": suffix,
        }
        particle_col = f"label_{suffix}"
        if _has_column(particles, particle_col):
            entry["particles"] = _count_values(particles, particle_col, empty_label=UNKNOWN_LABEL)
        sample_col = f"label_{suffix}"
        if _has_column(samples, sample_col):
            entry["samples_single"] = _count_values(samples, sample_col, empty_label=UNKNOWN_LABEL)
        sample_list_col = f"labels_{suffix}"
        if _has_column(samples, sample_list_col):
            entry["samples_multi"] = _count_list_values(samples, sample_list_col)
        layers[suffix] = entry
    return layers


def _summarize_similarity_groups(
    spec: LabelingSpec,
    particles: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    particle_counts = _count_fine_labels(particles)
    sample_counts = _count_fine_labels(samples)
    sample_multi_counts = _count_list_values(samples, "labels_fine") if _has_column(samples, "labels_fine") else {}

    groups: list[dict[str, Any]] = []
    for group in spec.similarity_groups:
        members = list(group.get("members") or [])
        counts = {
            "particles": _member_counts(members, particle_counts),
            "samples_single": _member_counts(members, sample_counts),
            "samples_multi": _member_counts(members, sample_multi_counts),
        }
        groups.append(
            {
                "name": group.get("name", ""),
                "description": group.get("description", ""),
                "members": members,
                "counts": counts,
                "totals": {
                    "particles": sum(counts["particles"].values()),
                    "samples_single": sum(counts["samples_single"].values()),
                    "samples_multi": sum(counts["samples_multi"].values()),
                },
            }
        )
    return groups


def _member_counts(members: Sequence[str], counts: Mapping[str, int]) -> dict[str, int]:
    return {str(member): int(counts.get(str(member), 0)) for member in members}


def _has_column(rows: Sequence[Mapping[str, Any]], column: str) -> bool:
    return any(column in row for row in rows)


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


def _dataset_id(
    *,
    schema_version: str,
    taxonomy_version: str,
    config_hash: str,
    labeling_spec_hash: str | None,
    metric_set_version: str | None,
) -> str:
    payload = {
        "config_hash": config_hash,
        "taxonomy_version": taxonomy_version,
        "labeling_spec_hash": labeling_spec_hash,
        "metric_set_version": metric_set_version,
    }
    digest = compute_config_hash({"dataset_id": payload})
    return f"{schema_version}_{taxonomy_version}_{digest}"


def _dataset_config_hash(
    *,
    seed: int,
    split_cfg: Mapping[str, Any],
    split_seed_offset: int,
    input_config_hash: str | None,
) -> str:
    payload = {
        "seed": seed,
        "split_seed_offset": split_seed_offset,
        "split": _split_config_payload(split_cfg),
        "input_config_hash": input_config_hash,
    }
    return compute_config_hash({"dataset": payload})


def _resolve_taxonomy_cfg(input_config: Mapping[str, Any] | None, cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    for source in [input_config, cfg]:
        if not isinstance(source, Mapping):
            continue
        wp_cfg = source.get("wafer_particles")
        if not isinstance(wp_cfg, Mapping):
            continue
        labels_cfg = wp_cfg.get("labels")
        if isinstance(labels_cfg, Mapping):
            return dict(labels_cfg)
    return None


def _resolve_metric_set_version(
    input_config: Mapping[str, Any] | None,
    cfg: Mapping[str, Any],
) -> str | None:
    for source in [input_config, cfg]:
        if not isinstance(source, Mapping):
            continue
        value = source.get("metric_set_version")
        if value not in (None, ""):
            return str(value)
        wp_cfg = source.get("wafer_particles")
        if not isinstance(wp_cfg, Mapping):
            continue
        value = wp_cfg.get("metric_set_version")
        if value not in (None, ""):
            return str(value)
        metrics_cfg = wp_cfg.get("metrics")
        if isinstance(metrics_cfg, Mapping):
            for key in ("metric_set_version", "set_version", "version"):
                candidate = metrics_cfg.get(key)
                if candidate not in (None, ""):
                    return str(candidate)
    return None


def _taxonomy_version(taxonomy_cfg: Mapping[str, Any] | None) -> str:
    if isinstance(taxonomy_cfg, Mapping):
        version = taxonomy_cfg.get("version")
        if version:
            return str(version)
    return "unknown"


def _taxonomy_snapshot(taxonomy_cfg: Mapping[str, Any] | None, *, domain: str) -> dict[str, Any]:
    if isinstance(taxonomy_cfg, Mapping):
        snapshot = dict(taxonomy_cfg)
        snapshot.setdefault("domain", domain)
        snapshot.setdefault("version", _taxonomy_version(taxonomy_cfg))
        return snapshot
    return {
        "version": "unknown",
        "domain": domain,
        "labels": [],
    }


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    text = yaml.safe_dump(dict(payload), sort_keys=True, allow_unicode=False)
    path.write_text(text, encoding="utf-8")


def _render_dataset_card(
    *,
    dataset_id: str,
    domain: str,
    schema_version: str,
    taxonomy_version: str,
    created_at: str,
    config_hash: str,
    dataset_config_hash: str,
    input_config_hash: str | None,
    labeling_spec_hash: str | None,
    metric_set_version: str | None,
    label_summary: Mapping[str, Any],
    particles_path: str,
    samples_path: str,
    index_samples_path: str,
    index_particles_path: str,
    split_counts: Mapping[str, Mapping[str, int]],
    split_ratios: Mapping[str, float],
) -> str:
    lines: list[str] = [
        "# Dataset Card",
        "",
        "## Overview",
        f"- dataset_id: {dataset_id}",
        f"- domain: {domain}",
        f"- schema_version: {schema_version}",
        f"- taxonomy_version: {taxonomy_version}",
        f"- created_at: {created_at}",
        "",
        "## Config",
        f"- config_hash: {config_hash}",
        f"- dataset_config_hash: {dataset_config_hash}",
    ]
    if input_config_hash:
        lines.append(f"- input_config_hash: {input_config_hash}")
    if labeling_spec_hash:
        lines.append(f"- labeling_spec_hash: {labeling_spec_hash}")
    if metric_set_version:
        lines.append(f"- metric_set_version: {metric_set_version}")
    lines.extend(
        [
            "",
            "## Files",
            f"- particles: {particles_path}",
            f"- samples: {samples_path}",
            f"- index_samples: {index_samples_path}",
            f"- index_particles: {index_particles_path}",
            "- splits: splits/splits.json",
            "- taxonomy_snapshot: taxonomy_snapshot.yaml",
            "- checksums: checksums.sha256",
        ]
    )
    lines.extend(["", "## Label Distribution", "### samples.label (primary)"])
    lines.extend(_format_distribution(label_summary.get("primary", {})))
    lines.extend(["", "### samples.label_fine (or label)"])
    lines.extend(_format_distribution(label_summary.get("fine_single", {})))
    fine_multi = label_summary.get("fine_multi")
    if fine_multi is not None:
        lines.extend(["", "### samples.labels_fine"])
        lines.extend(_format_distribution(fine_multi))
    layer_summary = label_summary.get("layers") or {}
    if layer_summary:
        lines.extend(["", "## Derived Label Layers"])
        for suffix, entry in sorted(layer_summary.items()):
            layer_name = entry.get("layer_name") or suffix
            lines.append(f"### {layer_name} ({suffix})")
            samples_single = entry.get("samples_single")
            if samples_single is not None:
                lines.append(f"#### samples.label_{suffix}")
                lines.extend(_format_distribution(samples_single))
            samples_multi = entry.get("samples_multi")
            if samples_multi is not None:
                lines.append(f"#### samples.labels_{suffix}")
                lines.extend(_format_distribution(samples_multi))
            particles_dist = entry.get("particles")
            if particles_dist is not None:
                lines.append(f"#### particles.label_{suffix}")
                lines.extend(_format_distribution(particles_dist))

    groups = label_summary.get("similarity_groups") or []
    if groups:
        lines.extend(["", "## Similarity Groups"])
        for group in groups:
            name = str(group.get("name") or "")
            members = ", ".join(str(member) for member in group.get("members", []))
            lines.append(f"### {name}")
            lines.append(f"- members: [{members}]")
            counts = group.get("counts", {})
            totals = group.get("totals", {})
            lines.append(f"- particles: {_format_member_counts(counts.get('particles', {}))}")
            lines.append(f"- samples_single: {_format_member_counts(counts.get('samples_single', {}))}")
            lines.append(f"- samples_multi: {_format_member_counts(counts.get('samples_multi', {}))}")
            lines.append(
                "- totals: particles={particles}, samples_single={samples_single}, samples_multi={samples_multi}".format(
                    particles=totals.get("particles", 0),
                    samples_single=totals.get("samples_single", 0),
                    samples_multi=totals.get("samples_multi", 0),
                )
            )

    ratios = ", ".join(f"{name}={value:.3f}" for name, value in sorted(split_ratios.items()))
    lines.extend(
        [
            "",
            "## Splits",
            f"- ratios: {ratios}",
        ]
    )
    for split_name, stats in sorted(split_counts.items()):
        lines.append(
            f"- {split_name}: n_samples={stats.get('n_samples', 0)}, n_particles={stats.get('n_particles', 0)}"
        )

    lines.extend(
        [
            "",
            "## Schema",
            "### particles",
        ]
    )
    for spec in PARTICLES_SCHEMA.required:
        lines.append(f"- {spec.name}: {spec.kind} (required)")
    for spec in PARTICLES_SCHEMA.optional:
        lines.append(f"- {spec.name}: {spec.kind} (optional)")

    lines.extend(
        [
            "",
            "### samples",
        ]
    )
    for spec in SAMPLES_SCHEMA.required:
        lines.append(f"- {spec.name}: {spec.kind} (required)")
    for spec in SAMPLES_SCHEMA.optional:
        lines.append(f"- {spec.name}: {spec.kind} (optional)")

    lines.append("")
    return "\n".join(lines)


def _format_distribution(counts: Mapping[str, int]) -> list[str]:
    if not counts:
        return ["- (empty)"]
    return [f"- {label}: {counts[label]}" for label in sorted(counts.keys())]


def _format_member_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "(empty)"
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts.keys()))


def _bundle_files(run_dir: Path, *, extra_rel_paths: Sequence[str]) -> list[Path]:
    files: set[Path] = set()
    for rel_dir in ["data", "splits"]:
        base = run_dir / rel_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                files.add(path)
    for rel in extra_rel_paths:
        path = run_dir / rel
        if path.exists() and path.is_file():
            files.add(path)
    return sorted(files, key=lambda path: path.relative_to(run_dir).as_posix())


def _write_checksums(path: Path, run_dir: Path, files: Sequence[Path]) -> None:
    entries: list[tuple[str, str]] = []
    for file_path in files:
        rel = file_path.relative_to(run_dir).as_posix()
        digest = _sha256_file(file_path)
        entries.append((rel, digest))
    entries.sort(key=lambda item: item[0])
    lines = [f"{digest}  {rel}" for rel, digest in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _package_format(package_cfg: Mapping[str, Any]) -> str:
    fmt = str(package_cfg.get("format", "none")).lower()
    if fmt in {"none", "zip", "tar.gz"}:
        return fmt
    raise ValueError("wafer_particles.export.package.format must be none|zip|tar.gz")


def _package_path(dataset_id: str, fmt: str) -> str:
    ext = "zip" if fmt == "zip" else "tar.gz"
    return f"data/dataset_{dataset_id}.{ext}"


def _write_package(
    run_dir: Path,
    rel_path: str,
    fmt: str,
    files: Sequence[Path],
) -> None:
    path = run_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "zip":
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _write_archive_entries(archive, run_dir, files)
        return
    if fmt == "tar.gz":
        with tarfile.open(path, "w:gz") as archive:
            _write_archive_entries(archive, run_dir, files)
        return
    raise ValueError(f"unsupported package format: {fmt}")


def _write_archive_entries(archive: Any, run_dir: Path, files: Sequence[Path]) -> None:
    for file_path in files:
        rel = file_path.relative_to(run_dir).as_posix()
        if isinstance(archive, zipfile.ZipFile):
            archive.write(file_path, arcname=rel)
        else:
            archive.add(file_path, arcname=rel)


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
