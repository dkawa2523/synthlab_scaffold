from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from synthlab.framework.artifacts import ArtifactReader
from synthlab.processes._wafer_particles_io import resolve_path


@dataclass(frozen=True)
class ModelInput:
    run_dir: Path | None
    model_dir: Path
    model_path: Path
    model_info: dict[str, Any] | None
    run_config: dict[str, Any] | None
    run_meta: dict[str, Any] | None


def resolve_model_input(
    model_cfg: Mapping[str, Any],
    *,
    repo_root: Path,
    default_process_name: str = "wafer_particles.process.train",
) -> ModelInput:
    run_dir = model_cfg.get("run_dir")
    model_path = model_cfg.get("model_path")
    run_config: dict[str, Any] | None = None
    run_meta: dict[str, Any] | None = None

    if run_dir:
        run_dir = resolve_path(run_dir, repo_root)
    else:
        run_name = model_cfg.get("run_name")
        if run_name:
            process_name = str(model_cfg.get("process_name", default_process_name))
            run_dir = repo_root / "runs" / str(run_name) / process_name

    if model_path:
        model_path = resolve_path(model_path, repo_root)
        model_dir = model_path.parent
    elif run_dir:
        if not run_dir.exists():
            raise ValueError(f"model run_dir not found: {run_dir}")
        reader = ArtifactReader(run_dir=run_dir)
        config_path = run_dir / "config" / "resolved.yaml"
        meta_path = run_dir / "meta" / "meta.json"
        if config_path.exists():
            run_config = reader.read_config()
        if meta_path.exists():
            run_meta = reader.read_meta()
        model_dir = run_dir / "model"
        model_path = model_dir / "model.json"
    else:
        raise ValueError("model input requires run_dir, run_name, or model_path")

    if not model_path.exists():
        raise ValueError(f"model file not found: {model_path}")

    model_info = json.loads(model_path.read_text(encoding="utf-8"))
    if not isinstance(model_info, Mapping):
        raise ValueError(f"model file must be a mapping: {model_path}")

    return ModelInput(
        run_dir=run_dir,
        model_dir=model_dir,
        model_path=model_path,
        model_info=dict(model_info),
        run_config=run_config,
        run_meta=run_meta,
    )


def model_input_payload(model_input: ModelInput) -> dict[str, Any]:
    return {
        "run_dir": str(model_input.run_dir) if model_input.run_dir else None,
        "model_dir": str(model_input.model_dir),
        "model_path": str(model_input.model_path),
    }
