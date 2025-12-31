from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from math import isnan, tau
from pathlib import Path
from typing import Any, Mapping

from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import (
    input_payload,
    read_manifest,
    read_table,
    resolve_input_paths,
)

_REQUIRED_PARTICLE_COLUMNS = (
    "sample_id",
    "particle_id",
    "r_mm",
    "theta_rad",
    "size_um",
    "label",
)


@dataclass(frozen=True)
class RangeSpec:
    min_value: float | None
    max_value: float | None
    min_exclusive: bool = False
    max_exclusive: bool = False


@register_process("wafer_particles.process.audit")
class AuditProcess(BaseProcess):
    name = "wafer_particles.process.audit"

    def run(self, writer) -> None:
        writer.log("audit start")
        wp_cfg = _resolve_wafer_particles_cfg(self.cfg)
        audit_cfg = _read_mapping(wp_cfg.get("audit"), "wafer_particles.audit")
        input_cfg = _read_mapping(audit_cfg.get("input"), "wafer_particles.audit.input")
        ranges = _resolve_ranges(audit_cfg)
        max_examples = _resolve_max_examples(audit_cfg)

        paths = resolve_input_paths(
            input_cfg,
            repo_root=writer.repo_root,
            default_process_name="wafer_particles.process.generate",
        )
        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)

        checks: list[dict[str, Any]] = []
        severity_counts = {"error": 0, "warn": 0, "info": 0}

        def add_check(name: str, severity: str, message: str, details: dict[str, Any] | None = None) -> None:
            entry = {"name": name, "severity": severity, "message": message}
            if details:
                entry["details"] = details
            checks.append(entry)
            if severity in severity_counts:
                severity_counts[severity] += 1

        if not particles:
            add_check(
                "particles.empty",
                "error",
                "particles table is empty",
            )
        else:
            _check_missing_columns(particles, add_check)
            _check_missing_values(particles, max_examples, add_check)
            _check_invalid_types(particles, max_examples, add_check)
            _check_ranges(particles, ranges, max_examples, add_check)
            _check_duplicates(
                particles,
                writer.run_dir / "metrics" / "audit_tables",
                max_examples,
                add_check,
            )

        _check_splits(paths, max_examples, add_check)

        audit_failed = severity_counts["error"] > 0
        payload = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": input_payload(paths),
            "ranges": {
                "r_mm": _range_payload(ranges["r_mm"]),
                "theta_rad": _range_payload(ranges["theta_rad"]),
                "size_um": _range_payload(ranges["size_um"]),
            },
            "summary": {
                "audit_failed": audit_failed,
                "error_count": severity_counts["error"],
                "warn_count": severity_counts["warn"],
                "info_count": severity_counts["info"],
                "n_particles": len(particles),
                "n_samples": len(samples),
            },
            "checks": checks,
        }
        writer.write_json("metrics/audit.json", payload)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=audit\n",
            encoding="utf-8",
        )
        writer.log("audit complete")


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


def _resolve_ranges(audit_cfg: Mapping[str, Any]) -> dict[str, RangeSpec]:
    ranges_cfg = _read_mapping(audit_cfg.get("ranges"), "wafer_particles.audit.ranges", required=False)
    r_cfg = _read_mapping(ranges_cfg.get("r_mm"), "wafer_particles.audit.ranges.r_mm", required=False)
    theta_cfg = _read_mapping(
        ranges_cfg.get("theta_rad"),
        "wafer_particles.audit.ranges.theta_rad",
        required=False,
    )
    size_cfg = _read_mapping(ranges_cfg.get("size_um"), "wafer_particles.audit.ranges.size_um", required=False)

    r_min = float(r_cfg.get("min", 0.0))
    r_max = float(r_cfg.get("max", 150.0))
    theta_min = float(theta_cfg.get("min", 0.0))
    theta_max = float(theta_cfg.get("max", tau))
    size_min = float(size_cfg.get("min", 0.0))
    size_min_exclusive = bool(size_cfg.get("min_exclusive", True))

    if r_max < r_min:
        raise ValueError("wafer_particles.audit.ranges.r_mm.max must be >= min")
    if theta_max < theta_min:
        raise ValueError("wafer_particles.audit.ranges.theta_rad.max must be >= min")

    return {
        "r_mm": RangeSpec(min_value=r_min, max_value=r_max),
        "theta_rad": RangeSpec(min_value=theta_min, max_value=theta_max),
        "size_um": RangeSpec(min_value=size_min, max_value=None, min_exclusive=size_min_exclusive),
    }


def _resolve_max_examples(audit_cfg: Mapping[str, Any]) -> int:
    report_cfg = _read_mapping(audit_cfg.get("report"), "wafer_particles.audit.report", required=False)
    max_examples = int(report_cfg.get("max_examples", 5))
    if max_examples < 0:
        raise ValueError("wafer_particles.audit.report.max_examples must be >= 0")
    return max_examples


def _check_missing_columns(
    particles: list[dict[str, Any]],
    add_check,
) -> None:
    present = set()
    for row in particles:
        present.update(row.keys())
    missing_columns = [col for col in _REQUIRED_PARTICLE_COLUMNS if col not in present]
    if missing_columns:
        add_check(
            "particles.missing_columns",
            "error",
            "required particle columns are missing",
            {"columns": missing_columns},
        )


def _check_missing_values(
    particles: list[dict[str, Any]],
    max_examples: int,
    add_check,
) -> None:
    missing_counts = {col: 0 for col in _REQUIRED_PARTICLE_COLUMNS}
    examples: dict[str, list[int]] = {col: [] for col in _REQUIRED_PARTICLE_COLUMNS}
    for idx, row in enumerate(particles):
        for col in _REQUIRED_PARTICLE_COLUMNS:
            value = row.get(col)
            if value is None or _is_nan(value):
                missing_counts[col] += 1
                if len(examples[col]) < max_examples:
                    examples[col].append(idx)
    missing_counts = {col: count for col, count in missing_counts.items() if count > 0}
    examples = {col: vals for col, vals in examples.items() if vals}
    if missing_counts:
        add_check(
            "particles.missing_values",
            "error",
            "missing values detected in required columns",
            {"missing_counts": missing_counts, "examples": examples},
        )


def _check_invalid_types(
    particles: list[dict[str, Any]],
    max_examples: int,
    add_check,
) -> None:
    invalid_counts = {"r_mm": 0, "theta_rad": 0, "size_um": 0}
    examples: dict[str, list[dict[str, Any]]] = {"r_mm": [], "theta_rad": [], "size_um": []}
    for idx, row in enumerate(particles):
        for col in invalid_counts:
            value = row.get(col)
            if value is None or _is_nan(value):
                continue
            if _is_number(value):
                continue
            invalid_counts[col] += 1
            if len(examples[col]) < max_examples:
                examples[col].append(
                    {
                        "row_index": idx,
                        "value": value,
                        "sample_id": row.get("sample_id"),
                        "particle_id": row.get("particle_id"),
                    }
                )
    invalid_counts = {col: count for col, count in invalid_counts.items() if count > 0}
    examples = {col: vals for col, vals in examples.items() if vals}
    if invalid_counts:
        add_check(
            "particles.invalid_types",
            "error",
            "non-numeric values detected in numeric columns",
            {"invalid_counts": invalid_counts, "examples": examples},
        )


def _check_ranges(
    particles: list[dict[str, Any]],
    ranges: dict[str, RangeSpec],
    max_examples: int,
    add_check,
) -> None:
    for column in ("r_mm", "theta_rad", "size_um"):
        spec = ranges[column]
        count = 0
        examples: list[dict[str, Any]] = []
        for idx, row in enumerate(particles):
            value = row.get(column)
            if value is None or _is_nan(value):
                continue
            if not _is_number(value):
                continue
            value = float(value)
            if _is_out_of_range(value, spec):
                count += 1
                if len(examples) < max_examples:
                    examples.append(
                        {
                            "row_index": idx,
                            "value": value,
                            "sample_id": row.get("sample_id"),
                            "particle_id": row.get("particle_id"),
                        }
                    )
        if count > 0:
            add_check(
                f"particles.range.{column}",
                "error",
                f"out-of-range values detected for {column}",
                {"count": count, "examples": examples},
            )


def _check_duplicates(
    particles: list[dict[str, Any]],
    tables_dir: Path,
    max_examples: int,
    add_check,
) -> None:
    pair_counts: dict[tuple[str, int], int] = {}
    row_counts: dict[str, int] = {}
    row_examples: dict[str, dict[str, Any]] = {}

    for row in particles:
        sample_id = row.get("sample_id")
        particle_id = row.get("particle_id")
        if sample_id is not None and particle_id is not None:
            try:
                pair = (str(sample_id), int(particle_id))
            except (TypeError, ValueError):
                pair = None
            if pair is not None:
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

        fingerprint = _row_fingerprint(row)
        row_counts[fingerprint] = row_counts.get(fingerprint, 0) + 1
        if fingerprint not in row_examples:
            row_examples[fingerprint] = row

    dup_pairs = [(pair, count) for pair, count in pair_counts.items() if count > 1]
    if dup_pairs:
        dup_pairs.sort(key=lambda item: item[1], reverse=True)
        example_pairs = [
            {"sample_id": pair[0], "particle_id": pair[1], "count": count}
            for pair, count in dup_pairs[:max_examples]
        ]
        duplicate_rows = sum(count - 1 for _, count in dup_pairs)
        add_check(
            "particles.duplicates.sample_particle",
            "error",
            "duplicate (sample_id, particle_id) pairs detected",
            {
                "duplicate_pairs": len(dup_pairs),
                "duplicate_rows": duplicate_rows,
                "examples": example_pairs,
            },
        )
        _write_duplicate_pairs_table(tables_dir, dup_pairs)

    dup_rows = [(fingerprint, count) for fingerprint, count in row_counts.items() if count > 1]
    if dup_rows:
        dup_rows.sort(key=lambda item: item[1], reverse=True)
        example_rows = [
            {
                "row_hash": fingerprint,
                "count": count,
                "row": row_examples.get(fingerprint),
            }
            for fingerprint, count in dup_rows[:max_examples]
        ]
        duplicate_rows = sum(count - 1 for _, count in dup_rows)
        add_check(
            "particles.duplicates.rows",
            "error",
            "fully duplicated particle rows detected",
            {
                "duplicate_groups": len(dup_rows),
                "duplicate_rows": duplicate_rows,
                "examples": example_rows,
            },
        )
        _write_duplicate_rows_table(tables_dir, dup_rows)


def _check_splits(paths, max_examples: int, add_check) -> None:
    splits_path = _resolve_splits_path(paths)
    if splits_path is None:
        add_check(
            "splits.not_found",
            "info",
            "splits file not found; leak check skipped",
        )
        return
    try:
        data = json.loads(splits_path.read_text(encoding="utf-8"))
    except Exception as exc:
        add_check(
            "splits.read_failed",
            "error",
            "failed to read splits file",
            {"path": str(splits_path), "error": str(exc)},
        )
        return
    sample_ids = data.get("sample_ids")
    if not isinstance(sample_ids, Mapping):
        add_check(
            "splits.invalid_format",
            "warn",
            "splits file missing sample_ids mapping",
            {"path": str(splits_path)},
        )
        return
    overlap_counts: dict[str, int] = {}
    overlap_examples: dict[str, list[str]] = {}
    split_names = sorted(sample_ids.keys())
    for idx, name_a in enumerate(split_names):
        ids_a = _coerce_id_list(sample_ids.get(name_a))
        if ids_a is None:
            continue
        set_a = set(ids_a)
        for name_b in split_names[idx + 1 :]:
            ids_b = _coerce_id_list(sample_ids.get(name_b))
            if ids_b is None:
                continue
            overlap = sorted(set_a.intersection(ids_b))
            if overlap:
                key = f"{name_a}|{name_b}"
                overlap_counts[key] = len(overlap)
                overlap_examples[key] = overlap[:max_examples]
    if overlap_counts:
        add_check(
            "splits.sample_id_overlap",
            "error",
            "sample_id overlap detected across splits",
            {"overlap_counts": overlap_counts, "examples": overlap_examples},
        )
    else:
        add_check(
            "splits.no_overlap",
            "info",
            "no sample_id overlap detected across splits",
        )


def _resolve_splits_path(paths) -> Path | None:
    if paths.run_dir:
        candidate = paths.run_dir / "splits" / "splits.json"
        if candidate.exists():
            return candidate
    if paths.manifest_path:
        manifest = read_manifest(paths.manifest_path)
        splits = manifest.get("splits")
        if isinstance(splits, Mapping) and splits.get("path"):
            rel = Path(str(splits["path"]))
            return paths.manifest_path.parent / rel
    return None


def _coerce_id_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [str(item) for item in value]


def _write_duplicate_pairs_table(path: Path, dup_pairs: list[tuple[tuple[str, int], int]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    table_path = path / "duplicate_sample_particle.csv"
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_id", "particle_id", "count"])
        for (sample_id, particle_id), count in dup_pairs:
            writer.writerow([sample_id, particle_id, count])


def _write_duplicate_rows_table(path: Path, dup_rows: list[tuple[str, int]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    table_path = path / "duplicate_rows.csv"
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row_hash", "count"])
        for row_hash, count in dup_rows:
            writer.writerow([row_hash, count])


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    payload = json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and isnan(value)


def _is_out_of_range(value: float, spec: RangeSpec) -> bool:
    if spec.min_value is not None:
        if spec.min_exclusive:
            if value <= spec.min_value:
                return True
        elif value < spec.min_value:
            return True
    if spec.max_value is not None:
        if spec.max_exclusive:
            if value >= spec.max_value:
                return True
        elif value > spec.max_value:
            return True
    return False


def _range_payload(spec: RangeSpec) -> dict[str, Any]:
    return {
        "min": spec.min_value,
        "max": spec.max_value,
        "min_exclusive": spec.min_exclusive,
        "max_exclusive": spec.max_exclusive,
    }


def _domain_name(cfg: Mapping[str, Any]) -> Any:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping):
        return domain.get("name")
    return domain or DOMAIN_NAME
