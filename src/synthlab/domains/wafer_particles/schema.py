from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin, tau
from typing import Any, Mapping, Sequence

DOMAIN_NAME = "wafer_particles"
SCHEMA_VERSION = "wafer_particles.v1"
_MAX_ERRORS = 10


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    kind: str
    required: bool = True
    min_value: float | None = None
    max_value: float | None = None

    def validate(self, value: Any) -> bool:
        if value is None:
            return False
        if self.kind == "str":
            return isinstance(value, str)
        if self.kind == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if self.kind == "float":
            return _is_float(value) and _within_range(float(value), self.min_value, self.max_value)
        raise ValueError(f"unknown kind: {self.kind}")


@dataclass(frozen=True)
class TableSchema:
    name: str
    required: tuple[ColumnSpec, ...]
    optional: tuple[ColumnSpec, ...] = ()

    def required_names(self) -> set[str]:
        return {spec.name for spec in self.required}

    def spec_for(self, column: str) -> ColumnSpec | None:
        for spec in self.required + self.optional:
            if spec.name == column:
                return spec
        return None


PARTICLES_SCHEMA = TableSchema(
    name="particles",
    required=(
        ColumnSpec("sample_id", "str"),
        ColumnSpec("particle_id", "int"),
        ColumnSpec("r_mm", "float"),
        ColumnSpec("theta_rad", "float", min_value=0.0, max_value=tau),
        ColumnSpec("size_um", "float"),
        ColumnSpec("label", "str"),
    ),
    optional=(
        ColumnSpec("x_mm", "float"),
        ColumnSpec("y_mm", "float"),
        ColumnSpec("component", "str"),
        ColumnSpec("source", "str"),
    ),
)

SAMPLES_SCHEMA = TableSchema(
    name="samples",
    required=(
        ColumnSpec("sample_id", "str"),
        ColumnSpec("label", "str"),
        ColumnSpec("n_particles", "int"),
        ColumnSpec("pattern_params", "str"),
        ColumnSpec("seed_offset", "int"),
    ),
)


class SchemaValidationError(ValueError):
    def __init__(self, table: str, errors: list[str]) -> None:
        message = f"{table} schema validation failed: " + "; ".join(errors)
        super().__init__(message)
        self.table = table
        self.errors = errors


def polar_to_cartesian_mm(r_mm: float, theta_rad: float) -> tuple[float, float]:
    """Single source of truth for r/theta -> x/y conversion."""
    return r_mm * cos(theta_rad), r_mm * sin(theta_rad)


def validate_particles_table(table: Any) -> None:
    validate_table(PARTICLES_SCHEMA, table)


def validate_samples_table(table: Any) -> None:
    validate_table(SAMPLES_SCHEMA, table)


def validate_table(schema: TableSchema, table: Any) -> None:
    errors: list[str] = []
    if isinstance(table, Mapping):
        _validate_columnar(schema, table, errors)
    else:
        _validate_rows(schema, table, errors)
    if errors:
        raise SchemaValidationError(schema.name, errors)


def build_manifest(
    *,
    particles_path: str,
    samples_path: str,
    particles_rows: int,
    samples_rows: int,
    label_distribution: Mapping[str, int] | None = None,
    schema_version: str = SCHEMA_VERSION,
    domain: str = DOMAIN_NAME,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "domain": domain,
        "files": {
            "particles": {"path": particles_path, "rows": particles_rows},
            "samples": {"path": samples_path, "rows": samples_rows},
        },
    }
    if label_distribution is not None:
        manifest["label_distribution"] = _normalize_label_distribution(label_distribution)
    validate_manifest(manifest, expected_schema_version=schema_version, expected_domain=domain)
    return manifest


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_schema_version: str | None = SCHEMA_VERSION,
    expected_domain: str | None = DOMAIN_NAME,
) -> None:
    errors: list[str] = []
    schema_version = manifest.get("schema_version")
    domain = manifest.get("domain")
    files = manifest.get("files")
    if not isinstance(schema_version, str) or not schema_version:
        errors.append("schema_version is required")
    elif expected_schema_version and schema_version != expected_schema_version:
        errors.append(f"schema_version mismatch: {schema_version}")
    if not isinstance(domain, str) or not domain:
        errors.append("domain is required")
    elif expected_domain and domain != expected_domain:
        errors.append(f"domain mismatch: {domain}")
    if not isinstance(files, Mapping):
        errors.append("files must be a mapping")
    else:
        _validate_manifest_file(files, "particles", errors)
        _validate_manifest_file(files, "samples", errors)
    if "label_distribution" in manifest:
        if not _is_label_distribution(manifest["label_distribution"]):
            errors.append("label_distribution must be a mapping of str to int")
    if errors:
        raise ValueError("manifest validation failed: " + "; ".join(errors))


def _validate_manifest_file(files: Mapping[str, Any], key: str, errors: list[str]) -> None:
    entry = files.get(key)
    if not isinstance(entry, Mapping):
        errors.append(f"files.{key} must be a mapping")
        return
    path = entry.get("path")
    rows = entry.get("rows")
    if not isinstance(path, str) or not path:
        errors.append(f"files.{key}.path is required")
    if not isinstance(rows, int) or isinstance(rows, bool):
        errors.append(f"files.{key}.rows must be int")


def _validate_rows(schema: TableSchema, rows: Any, errors: list[str]) -> None:
    if rows is None:
        errors.append("table is None")
        return
    for idx, row in enumerate(rows):
        if len(errors) >= _MAX_ERRORS:
            return
        if not isinstance(row, Mapping):
            errors.append(f"row {idx} is not a mapping")
            continue
        for name in schema.required_names():
            if name not in row:
                errors.append(f"row {idx} missing {name}")
                if len(errors) >= _MAX_ERRORS:
                    return
        for col_name, value in row.items():
            spec = schema.spec_for(col_name)
            if spec is None:
                continue
            if not spec.validate(value):
                errors.append(f"row {idx} invalid {col_name}")
                if len(errors) >= _MAX_ERRORS:
                    return


def _validate_columnar(schema: TableSchema, table: Mapping[str, Any], errors: list[str]) -> None:
    for name in schema.required_names():
        if name not in table:
            errors.append(f"missing column {name}")
    if errors:
        return
    length: int | None = None
    for col_name, values in table.items():
        if not _is_sequence(values):
            errors.append(f"column {col_name} is not a sequence")
            if len(errors) >= _MAX_ERRORS:
                return
            continue
        if length is None:
            length = len(values)
        elif len(values) != length:
            errors.append("column lengths do not match")
            if len(errors) >= _MAX_ERRORS:
                return
        spec = schema.spec_for(col_name)
        if spec is None:
            continue
        for idx, value in enumerate(values):
            if not spec.validate(value):
                errors.append(f"column {col_name} invalid at {idx}")
                if len(errors) >= _MAX_ERRORS:
                    return


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _is_float(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _within_range(value: float, min_value: float | None, max_value: float | None) -> bool:
    if min_value is not None and value < min_value:
        return False
    if max_value is not None and value > max_value:
        return False
    return True


def _normalize_label_distribution(label_distribution: Mapping[str, int]) -> dict[str, int]:
    if not _is_label_distribution(label_distribution):
        raise ValueError("label_distribution must be a mapping of str to int")
    return {str(key): int(value) for key, value in label_distribution.items()}


def _is_label_distribution(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    for key, count in value.items():
        if not isinstance(key, str):
            return False
        if not isinstance(count, int) or isinstance(count, bool):
            return False
    return True
