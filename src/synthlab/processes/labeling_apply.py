from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping, Sequence

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    PARTICLES_SCHEMA,
    SAMPLES_SCHEMA,
    SCHEMA_VERSION,
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
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._export_io import export_input_payload, resolve_export_input
from synthlab.processes._wafer_particles_io import read_table, resolve_path


@register_process("wafer_particles.process.labeling_apply")
class LabelingApplyProcess(BaseProcess):
    name = "wafer_particles.process.labeling_apply"

    def run(self, writer) -> None:
        writer.log("labeling_apply start")
        wp_cfg = _resolve_wafer_particles_cfg(self.cfg)
        apply_cfg = _resolve_labeling_apply_cfg(wp_cfg)
        input_cfg = _read_mapping(apply_cfg.get("input"), "wafer_particles.labeling_apply.input")
        export_input = resolve_export_input(input_cfg, repo_root=writer.repo_root)

        particles = read_table(export_input.particles_path)
        samples = read_table(export_input.samples_path)
        validate_particles_table(particles)
        validate_samples_table(samples)

        spec_path = _resolve_labeling_spec_path(wp_cfg, writer.repo_root)
        labeling_spec = LabelingSpec.load(spec_path)
        labeling_spec.apply_to_particles(particles)
        labeling_spec.apply_to_samples(samples)

        summary_layers = _summarize_layers(labeling_spec, particles, samples)
        summary_groups = _summarize_similarity_groups(labeling_spec, particles, samples)

        list_columns = _label_list_columns(labeling_spec)
        serialize_label_lists(samples, list_columns)

        io_cfg = _read_mapping(wp_cfg.get("io"), "wafer_particles.io")
        fmt_raw = str(io_cfg.get("format", "auto")).lower()
        fmt, auto_selected = _resolve_output_format(fmt_raw)
        if auto_selected:
            writer.log(f"io.format=auto resolved to {fmt}")
        csv_cfg = _read_mapping(io_cfg.get("csv"), "wafer_particles.io.csv", required=False)
        parquet_cfg = _read_mapping(io_cfg.get("parquet"), "wafer_particles.io.parquet", required=False)
        particles_path, samples_path = _data_paths(fmt)

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

        label_distribution = _label_distribution(samples)
        manifest = build_manifest(
            particles_path=particles_path,
            samples_path=samples_path,
            particles_rows=len(particles),
            samples_rows=len(samples),
            label_distribution=label_distribution,
            schema_version=str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            domain=_domain_name(self.cfg),
        )
        writer.write_json("manifest.json", manifest)

        _write_labeling_spec_meta(writer.run_dir / "meta", labeling_spec)

        payload_base = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": export_input_payload(export_input),
            "labeling_spec_hash": labeling_spec.hash(),
            "unknown_label": UNKNOWN_LABEL,
        }
        writer.write_json(
            "reports/labeling_layers_summary.json",
            {**payload_base, **summary_layers},
        )
        writer.write_json(
            "reports/similarity_groups_summary.json",
            {**payload_base, **summary_groups},
        )
        writer.write_json(
            "metrics/labeling_apply_summary.json",
            {
                **payload_base,
                "n_particles": len(particles),
                "n_samples": len(samples),
                "layers": sorted(summary_layers.get("layers", {}).keys()),
            },
        )
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=labeling_apply\n",
            encoding="utf-8",
        )
        writer.log("labeling_apply complete")


def _resolve_wafer_particles_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    return dict(wp_cfg)


def _resolve_labeling_apply_cfg(wp_cfg: Mapping[str, Any]) -> dict[str, Any]:
    apply_cfg = wp_cfg.get("labeling_apply")
    if not isinstance(apply_cfg, Mapping):
        raise ValueError("wafer_particles.labeling_apply config is required")
    return dict(apply_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _resolve_labeling_spec_path(wp_cfg: Mapping[str, Any], repo_root: Path) -> Path:
    labeling_cfg = _read_mapping(wp_cfg.get("labeling"), "wafer_particles.labeling")
    spec_path = labeling_cfg.get("spec_path")
    if not spec_path:
        raise ValueError("wafer_particles.labeling.spec_path is required")
    return resolve_path(spec_path, repo_root)


def _write_labeling_spec_meta(meta_dir: Path, spec: LabelingSpec) -> None:
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "labeling_spec.yaml").write_text(spec.to_yaml(), encoding="utf-8")
    (meta_dir / "labeling_spec_hash.txt").write_text(spec.hash() + "\n", encoding="utf-8")


def _resolve_output_format(fmt: str) -> tuple[str, bool]:
    if fmt != "auto":
        return fmt, False
    try:
        import pyarrow  # noqa: F401
    except Exception:
        return "csv", True
    return "parquet", True


def _data_paths(fmt: str) -> tuple[str, str]:
    if fmt == "csv":
        return ("data/particles.csv", "data/samples.csv")
    if fmt == "parquet":
        return ("data/particles.parquet", "data/samples.parquet")
    raise ValueError(f"unsupported io.format: {fmt}")


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


def _label_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for row in rows:
        label = row.get("label")
        if label in (None, ""):
            label = row.get("label_fine")
        if label in (None, ""):
            continue
        key = str(label)
        dist[key] = dist.get(key, 0) + 1
    return dist


def _summarize_layers(
    spec: LabelingSpec,
    particles: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    layers: dict[str, Any] = {}
    for layer_name, _mapping in spec.layers.items():
        suffix = spec.layer_columns[layer_name]
        entry: dict[str, Any] = {
            "layer_name": layer_name,
            "column_suffix": suffix,
        }
        particle_col = f"label_{suffix}"
        if particles:
            entry["particles"] = {
                "column": particle_col,
                "counts": _count_values(particles, particle_col),
            }
        sample_col = f"label_{suffix}"
        if _has_column(samples, sample_col):
            entry["samples_single"] = {
                "column": sample_col,
                "counts": _count_values(samples, sample_col),
            }
        sample_list_col = f"labels_{suffix}"
        if _has_column(samples, sample_list_col):
            entry["samples_multi"] = {
                "column": sample_list_col,
                "counts": _count_list_values(samples, sample_list_col),
            }
        layers[suffix] = entry
    return {"layers": layers}


def _summarize_similarity_groups(
    spec: LabelingSpec,
    particles: Sequence[Mapping[str, Any]],
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
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

    causes: dict[str, Any] = {}
    for cause_id, payload in spec.cause_hypotheses.items():
        members = list(payload.get("related_labels") or [])
        counts = {
            "particles": _member_counts(members, particle_counts),
            "samples_single": _member_counts(members, sample_counts),
            "samples_multi": _member_counts(members, sample_multi_counts),
        }
        causes[str(cause_id)] = {
            **payload,
            "counts": counts,
            "totals": {
                "particles": sum(counts["particles"].values()),
                "samples_single": sum(counts["samples_single"].values()),
                "samples_multi": sum(counts["samples_multi"].values()),
            },
        }

    return {
        "similarity_groups": groups,
        "cause_hypotheses": causes,
    }


def _count_values(rows: Sequence[Mapping[str, Any]], column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(column)
        key = UNKNOWN_LABEL if value in (None, "") else str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_list_values(rows: Sequence[Mapping[str, Any]], column: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        labels = normalize_label_list(row.get(column))
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
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


def _member_counts(members: Sequence[str], counts: Mapping[str, int]) -> dict[str, int]:
    return {str(member): int(counts.get(str(member), 0)) for member in members}


def _has_column(rows: Sequence[Mapping[str, Any]], column: str) -> bool:
    return any(column in row for row in rows)


def _label_list_columns(spec: LabelingSpec) -> list[str]:
    return [f"labels_{suffix}" for suffix in spec.layer_columns.values()]


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
