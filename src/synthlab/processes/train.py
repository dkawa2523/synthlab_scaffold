from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from synthlab.domains.wafer_particles import SCHEMA_VERSION
from synthlab.framework.artifacts import compute_config_hash
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import get_model, register_process
from synthlab.processes._export_io import export_input_payload, resolve_export_input

import synthlab.domains.wafer_particles.models  # noqa: F401


@register_process("wafer_particles.process.train")
class TrainProcess(BaseProcess):
    name = "wafer_particles.process.train"

    def run(self, writer) -> None:
        writer.log("train start")
        train_cfg = _resolve_train_cfg(self.cfg)
        input_cfg = _read_mapping(train_cfg.get("input"), "wafer_particles.train.input")
        export_input = resolve_export_input(input_cfg, repo_root=writer.repo_root)
        dataset_id = _require_dataset_id(export_input.manifest)

        model_cfg = _read_mapping(train_cfg.get("model"), "wafer_particles.train.model")
        model_name = _require_name(model_cfg.get("name"), "wafer_particles.train.model.name")

        seed = _coerce_int(self.cfg.get("seed"), "seed")
        train_seed = _derive_seed(seed, 0, "train_model")

        model_dir = writer.run_dir / "model"
        preds_dir = writer.run_dir / "preds"
        model_dir.mkdir(parents=True, exist_ok=True)
        preds_dir.mkdir(parents=True, exist_ok=True)

        result = _run_model_plugin(
            model_name,
            model_cfg,
            export_input,
            stage="train",
            seed=train_seed,
            model_dir=model_dir,
            preds_dir=preds_dir,
        )
        model_metrics = _read_mapping(result.get("metrics"), "model.metrics", required=False)

        model_info = _merge_model_info(
            result.get("model_info"),
            model_name=model_name,
            model_cfg=model_cfg,
            dataset_id=dataset_id,
            schema_version=str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            domain=_domain_name(self.cfg),
            train_seed=train_seed,
        )
        writer.write_json("model/model.json", model_info)

        preds = _ensure_list(result.get("preds"))
        preds_payload = _preds_payload(
            preds,
            stage="train",
            dataset_id=dataset_id,
            schema_version=str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            domain=_domain_name(self.cfg),
        )
        writer.write_json("preds/train_predictions.json", preds_payload)

        metrics = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "dataset_id": dataset_id,
            "input": export_input_payload(export_input),
            "export_config_hash": export_input.manifest.get("config_hash"),
            "input_config_hash": export_input.manifest.get("input_config_hash"),
            "model": {
                "name": model_name,
                "config_hash": compute_config_hash({"model": model_cfg}),
            },
            "seed": seed,
            "seed_policy": str(train_cfg.get("seed_policy", "fixed")),
            "train_seed": train_seed,
            "metrics": model_metrics,
        }
        writer.write_json("metrics/train_summary.json", metrics)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=train\n",
            encoding="utf-8",
        )
        writer.log("train complete")


def _resolve_train_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    train_cfg = wp_cfg.get("train")
    if not isinstance(train_cfg, Mapping):
        raise ValueError("wafer_particles.train config is required")
    return dict(train_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _require_name(value: Any, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return str(value)


def _require_dataset_id(manifest: Mapping[str, Any]) -> str:
    dataset_id = manifest.get("dataset_id")
    if not dataset_id:
        raise ValueError("dataset_id is required in export manifest")
    return str(dataset_id)


def _coerce_int(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an int")


def _derive_seed(base_seed: int, offset: int, component: str) -> int:
    payload = f"{base_seed}:{offset}:{component}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(base_seed) + int(digest[:12], 16)


def _run_model_plugin(
    model_name: str,
    model_cfg: Mapping[str, Any],
    export_input,
    *,
    stage: str,
    seed: int,
    model_dir: Path,
    preds_dir: Path,
) -> dict[str, Any]:
    model = get_model(model_name)
    result = model(
        model_cfg,
        {
            "manifest": export_input.manifest,
            "input": export_input_payload(export_input),
        },
        stage=stage,
        seed=seed,
        model_dir=model_dir,
        preds_dir=preds_dir,
    )
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        raise ValueError("model plugin must return a mapping")
    return dict(result)


def _merge_model_info(
    model_info: Any,
    *,
    model_name: str,
    model_cfg: Mapping[str, Any],
    dataset_id: str,
    schema_version: str,
    domain: Any,
    train_seed: int,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(model_info, Mapping):
        merged.update(model_info)
    merged.setdefault("model_name", model_name)
    merged.setdefault("model_config_hash", compute_config_hash({"model": model_cfg}))
    merged.setdefault("dataset_id", dataset_id)
    merged.setdefault("schema_version", schema_version)
    merged.setdefault("domain", domain)
    merged.setdefault("train_seed", train_seed)
    return merged


def _preds_payload(
    preds: list[Any],
    *,
    stage: str,
    dataset_id: str,
    schema_version: str,
    domain: Any,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "dataset_id": dataset_id,
        "schema_version": schema_version,
        "domain": domain,
        "preds": preds,
    }


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ValueError("preds must be a list when provided")


def _domain_name(cfg: Mapping[str, Any]) -> Any:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping):
        return domain.get("name")
    return domain
