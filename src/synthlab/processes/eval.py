from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from synthlab.domains.wafer_particles import SCHEMA_VERSION
from synthlab.framework.artifacts import compute_config_hash
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import get_model, register_process
from synthlab.processes._export_io import export_input_payload, resolve_export_input
from synthlab.processes._model_io import model_input_payload, resolve_model_input

import synthlab.domains.wafer_particles.models  # noqa: F401


@register_process("wafer_particles.process.eval")
class EvalProcess(BaseProcess):
    name = "wafer_particles.process.eval"

    def run(self, writer) -> None:
        writer.log("eval start")
        eval_cfg = _resolve_eval_cfg(self.cfg)
        input_cfg = _read_mapping(eval_cfg.get("input"), "wafer_particles.eval.input")
        data_cfg = _read_mapping(input_cfg.get("data"), "wafer_particles.eval.input.data")
        model_cfg = _read_mapping(input_cfg.get("model"), "wafer_particles.eval.input.model")

        export_input = resolve_export_input(data_cfg, repo_root=writer.repo_root)
        model_input = resolve_model_input(model_cfg, repo_root=writer.repo_root)
        dataset_id = _require_dataset_id(export_input.manifest)

        seed = _coerce_int(self.cfg.get("seed"), "seed")
        eval_seed = _derive_seed(seed, 0, "eval_model")

        eval_config_hash = _evaluation_config_hash(eval_cfg)
        seed_policy = str(eval_cfg.get("seed_policy", "fixed"))

        model_name = _resolve_model_name(eval_cfg, model_input)
        model_result: dict[str, Any] = {}
        preds_dir = writer.run_dir / "preds"
        preds_dir.mkdir(parents=True, exist_ok=True)
        if model_name:
            model_result = _run_model_plugin(
                model_name,
                eval_cfg.get("model") if isinstance(eval_cfg.get("model"), Mapping) else {},
                export_input,
                model_input,
                stage="eval",
                seed=eval_seed,
                model_dir=model_input.model_dir,
                preds_dir=preds_dir,
            )

        model_metrics = _read_mapping(model_result.get("metrics"), "model.metrics", required=False)
        preds = _ensure_list(model_result.get("preds"))
        preds_payload = _preds_payload(
            preds,
            stage="eval",
            dataset_id=dataset_id,
            schema_version=str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            domain=_domain_name(self.cfg),
        )
        writer.write_json("preds/eval_predictions.json", preds_payload)

        metrics = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "dataset_id": dataset_id,
            "input": {
                "data": export_input_payload(export_input),
                "model": model_input_payload(model_input),
            },
            "model": {
                "name": model_name,
                "model_path": str(model_input.model_path),
            },
            "seed": seed,
            "seed_policy": seed_policy,
            "eval_seed": eval_seed,
            "eval_config_hash": eval_config_hash,
            "metrics": model_metrics,
        }
        writer.write_json("metrics/eval_summary.json", metrics)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=eval\n",
            encoding="utf-8",
        )
        writer.log("eval complete")


def _resolve_eval_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    eval_cfg = wp_cfg.get("eval")
    if not isinstance(eval_cfg, Mapping):
        raise ValueError("wafer_particles.eval config is required")
    return dict(eval_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


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


def _evaluation_config_hash(eval_cfg: Mapping[str, Any]) -> str:
    trimmed = dict(eval_cfg)
    for key in ["input", "model", "output"]:
        trimmed.pop(key, None)
    return compute_config_hash({"eval": trimmed})


def _resolve_model_name(eval_cfg: Mapping[str, Any], model_input) -> str | None:
    model_cfg = eval_cfg.get("model")
    if isinstance(model_cfg, Mapping):
        name = model_cfg.get("name")
        if name:
            return str(name)
    model_info = model_input.model_info or {}
    name = model_info.get("model_name") or model_info.get("name")
    if name:
        return str(name)
    return None


def _run_model_plugin(
    model_name: str,
    model_cfg: Mapping[str, Any],
    export_input,
    model_input,
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
            "model": model_input.model_info,
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
