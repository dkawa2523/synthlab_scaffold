from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION, validate_manifest
from synthlab.processes._wafer_particles_io import (
    input_payload,
    read_manifest,
    resolve_input_paths,
    resolve_path,
)


@dataclass(frozen=True)
class ExportInput:
    run_dir: Path | None
    manifest_path: Path
    particles_path: Path
    samples_path: Path
    splits_path: Path | None
    index_samples_path: Path | None
    index_particles_path: Path | None
    input_config: dict[str, Any] | None
    manifest: dict[str, Any]


def resolve_export_input(input_cfg: Mapping[str, Any], *, repo_root: Path) -> ExportInput:
    paths = resolve_input_paths(
        input_cfg,
        repo_root=repo_root,
        default_process_name="wafer_particles.process.export",
    )
    if paths.manifest_path is None:
        raise ValueError("export input requires run_dir or manifest_path")
    manifest = read_manifest(paths.manifest_path)
    validate_manifest(
        manifest,
        expected_schema_version=SCHEMA_VERSION,
        expected_domain=DOMAIN_NAME,
    )
    base_dir = paths.manifest_path.parent

    splits_path = _manifest_path(manifest.get("splits"), base_dir)
    files = manifest.get("files")
    index_samples_path = _manifest_file_path(files, "index_samples", base_dir)
    index_particles_path = _manifest_file_path(files, "index_particles", base_dir)

    overrides = _read_overrides(input_cfg, repo_root)
    splits_path = overrides.get("splits_path", splits_path)
    index_samples_path = overrides.get("index_samples_path", index_samples_path)
    index_particles_path = overrides.get("index_particles_path", index_particles_path)

    return ExportInput(
        run_dir=paths.run_dir,
        manifest_path=paths.manifest_path,
        particles_path=paths.particles_path,
        samples_path=paths.samples_path,
        splits_path=splits_path,
        index_samples_path=index_samples_path,
        index_particles_path=index_particles_path,
        input_config=paths.input_config,
        manifest=manifest,
    )


def export_input_payload(export_input: ExportInput) -> dict[str, Any]:
    payload = input_payload(
        export_input,
    )
    payload["splits_path"] = str(export_input.splits_path) if export_input.splits_path else None
    payload["index_samples_path"] = (
        str(export_input.index_samples_path) if export_input.index_samples_path else None
    )
    payload["index_particles_path"] = (
        str(export_input.index_particles_path) if export_input.index_particles_path else None
    )
    return payload


def _manifest_path(section: Any, base_dir: Path) -> Path | None:
    if not isinstance(section, Mapping):
        return None
    path = section.get("path")
    if not path:
        return None
    return base_dir / str(path)


def _manifest_file_path(files: Any, key: str, base_dir: Path) -> Path | None:
    if not isinstance(files, Mapping):
        return None
    entry = files.get(key)
    if not isinstance(entry, Mapping):
        return None
    path = entry.get("path")
    if not path:
        return None
    return base_dir / str(path)


def _read_overrides(input_cfg: Mapping[str, Any], repo_root: Path) -> dict[str, Path | None]:
    overrides: dict[str, Path | None] = {}
    splits_path = input_cfg.get("splits_path")
    if splits_path:
        overrides["splits_path"] = resolve_path(splits_path, repo_root)
    index_samples_path = input_cfg.get("index_samples_path")
    if index_samples_path:
        overrides["index_samples_path"] = resolve_path(index_samples_path, repo_root)
    index_particles_path = input_cfg.get("index_particles_path")
    if index_particles_path:
        overrides["index_particles_path"] = resolve_path(index_particles_path, repo_root)
    return overrides
