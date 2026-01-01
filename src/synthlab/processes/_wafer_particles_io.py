from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION, validate_manifest
from synthlab.framework.artifacts import ArtifactReader


@dataclass(frozen=True)
class InputPaths:
    run_dir: Path | None
    manifest_path: Path | None
    particles_path: Path
    samples_path: Path
    input_config: dict[str, Any] | None


def resolve_input_paths(
    input_cfg: Mapping[str, Any],
    *,
    repo_root: Path,
    default_process_name: str = "wafer_particles.process.generate",
) -> InputPaths:
    run_dir = input_cfg.get("run_dir")
    manifest_path = input_cfg.get("manifest_path")
    particles_path = input_cfg.get("particles_path")
    samples_path = input_cfg.get("samples_path")
    input_config: dict[str, Any] | None = None

    if run_dir:
        run_dir = resolve_path(run_dir, repo_root)
    else:
        run_name = input_cfg.get("run_name")
        if run_name:
            process_name = str(input_cfg.get("process_name", default_process_name))
            run_dir = repo_root / "runs" / str(run_name) / process_name

    if run_dir is not None:
        if not run_dir.exists():
            raise ValueError(f"input run_dir not found: {run_dir}")
        reader = ArtifactReader(run_dir=run_dir)
        config_path = run_dir / "config" / "resolved.yaml"
        if config_path.exists():
            input_config = reader.read_config()
        manifest_path = find_manifest(run_dir)
        if manifest_path:
            particles_path, samples_path = paths_from_manifest(
                manifest_path,
                expected_schema_version=SCHEMA_VERSION,
                expected_domain=DOMAIN_NAME,
            )
        else:
            particles_path = resolve_data_path(run_dir, particles_path, ["particles.parquet", "particles.csv"])
            samples_path = resolve_data_path(run_dir, samples_path, ["samples.parquet", "samples.csv"])
    elif manifest_path:
        manifest_path = resolve_path(manifest_path, repo_root)
        particles_path, samples_path = paths_from_manifest(
            manifest_path,
            expected_schema_version=SCHEMA_VERSION,
            expected_domain=DOMAIN_NAME,
        )
    else:
        if not particles_path or not samples_path:
            raise ValueError("input requires run_dir, manifest_path, or particles_path+samples_path")
        particles_path = resolve_path(particles_path, repo_root)
        samples_path = resolve_path(samples_path, repo_root)

    if particles_path is None or samples_path is None:
        raise ValueError("input paths could not be resolved")
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


def resolve_path(value: Any, base: Path) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path


def resolve_data_path(run_dir: Path, value: Any, candidates: list[str]) -> Path:
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


def find_manifest(run_dir: Path) -> Path | None:
    for name in ["manifest.json", "manifest.yaml", "manifest.yml"]:
        path = run_dir / name
        if path.exists():
            return path
    return None


def paths_from_manifest(
    manifest_path: Path,
    *,
    expected_schema_version: str,
    expected_domain: str,
) -> tuple[Path, Path]:
    manifest = read_manifest(manifest_path)
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


def read_manifest(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"manifest must be a mapping: {path}")
    return dict(data)


def read_table(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return read_csv(path)
    if path.suffix.lower() == ".parquet":
        return read_parquet(path)
    raise ValueError(f"unsupported table format: {path.suffix}")


def read_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(coerce_row(row))
    return rows


def coerce_row(row: Mapping[str, Any]) -> dict[str, Any]:
    typed: dict[str, Any] = {}
    for key, value in row.items():
        if value is None or value == "":
            typed[key] = None
            continue
        if key in {"particle_id", "n_particles", "seed_offset", "component_id", "is_size_anomaly"}:
            typed[key] = int(value)
        elif key in {"r_norm", "r_mm", "theta_rad", "size_um", "x_mm", "y_mm"}:
            typed[key] = float(value)
        else:
            typed[key] = str(value)
    return typed


def read_parquet(path: Path) -> list[dict[str, Any]]:
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


def input_payload(paths: InputPaths) -> dict[str, Any]:
    return {
        "run_dir": str(paths.run_dir) if paths.run_dir else None,
        "manifest_path": str(paths.manifest_path) if paths.manifest_path else None,
        "particles_path": str(paths.particles_path),
        "samples_path": str(paths.samples_path),
    }
