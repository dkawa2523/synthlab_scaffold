from __future__ import annotations

import importlib
import platform
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Mapping

from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process


def _torch_info() -> Dict[str, Any]:
    try:
        import torch
    except Exception as exc:  # pragma: no cover - optional dependency
        return {
            "available": False,
            "cuda_available": False,
            "error": str(exc),
        }
    return {
        "available": True,
        "version": getattr(torch, "__version__", "unknown"),
        "cuda_available": bool(torch.cuda.is_available()),
    }


def _module_info(name: str) -> Dict[str, Any]:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # pragma: no cover - optional dependency
        return {
            "available": False,
            "error": str(exc),
        }
    version = getattr(module, "__version__", None)
    return {
        "available": True,
        "version": version or "unknown",
    }


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == "???"


def _resolve_process_name(cfg: Mapping[str, Any]) -> str | None:
    proc = cfg.get("process")
    if isinstance(proc, Mapping):
        return str(proc.get("name") or "")
    if isinstance(proc, str):
        return proc
    return None


def _resolve_domain_name(cfg: Mapping[str, Any]) -> str | None:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping):
        return str(domain.get("name") or "")
    if isinstance(domain, str):
        return domain
    return None


def _resolve_io_format(cfg: Mapping[str, Any]) -> str | None:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        return None
    io_cfg = wp_cfg.get("io")
    if not isinstance(io_cfg, Mapping):
        return None
    fmt = io_cfg.get("format")
    if fmt is None:
        return None
    return str(fmt).lower()


@register_process("wafer_particles.process.doctor")
class DoctorProcess(BaseProcess):
    name = "wafer_particles.process.doctor"

    def run(self, writer) -> None:
        writer.log("doctor start")
        checks: list[dict[str, Any]] = []

        def add_check(name: str, status: str, message: str, *, value: Any | None = None) -> None:
            entry = {"name": name, "status": status, "message": message}
            if value is not None:
                entry["value"] = value
            checks.append(entry)

        cfg = self.cfg
        seed = cfg.get("seed")
        if _is_missing(seed):
            add_check("config.seed", "error", "seed is required for determinism")
        else:
            try:
                seed_value = int(seed)
            except (TypeError, ValueError):
                add_check("config.seed", "error", "seed must be an int")
            else:
                add_check("config.seed", "ok", "seed is set", value=seed_value)

        schema_version = cfg.get("schema_version")
        if _is_missing(schema_version):
            add_check("config.schema_version", "error", "schema_version is required")
        else:
            add_check("config.schema_version", "ok", "schema_version is set", value=str(schema_version))

        run_name = cfg.get("run_name")
        if _is_missing(run_name):
            add_check("config.run_name", "error", "run_name is required")
        else:
            add_check("config.run_name", "ok", "run_name is set", value=str(run_name))

        process_name = _resolve_process_name(cfg)
        if _is_missing(process_name):
            add_check("config.process", "error", "process.name is required")
        else:
            add_check("config.process", "ok", "process is set", value=str(process_name))

        domain_name = _resolve_domain_name(cfg)
        if _is_missing(domain_name):
            add_check("config.domain", "error", "domain.name is required")
        else:
            add_check("config.domain", "ok", "domain is set", value=str(domain_name))

        dependencies = {
            "pyarrow": _module_info("pyarrow"),
            "matplotlib": _module_info("matplotlib"),
            "yaml": _module_info("yaml"),
            "torch": _torch_info(),
        }

        io_format = _resolve_io_format(cfg)
        if io_format == "parquet":
            if not dependencies["pyarrow"]["available"]:
                add_check(
                    "dependency.pyarrow",
                    "error",
                    "pyarrow is required for parquet I/O (use wafer_particles.io.format=csv).",
                )
            else:
                add_check("dependency.pyarrow", "ok", "pyarrow available for parquet")
        elif io_format == "csv":
            add_check("dependency.pyarrow", "ok", "csv selected; pyarrow optional")
        elif io_format == "auto":
            if dependencies["pyarrow"]["available"]:
                add_check("dependency.pyarrow", "ok", "auto selected; parquet available")
            else:
                add_check("dependency.pyarrow", "ok", "auto selected; falling back to csv")

        if process_name == "wafer_particles.process.viz":
            if not dependencies["matplotlib"]["available"]:
                add_check("dependency.matplotlib", "error", "matplotlib is required for viz process")
            else:
                add_check("dependency.matplotlib", "ok", "matplotlib available for viz")
        else:
            if not dependencies["matplotlib"]["available"]:
                add_check("dependency.matplotlib", "warn", "matplotlib not installed (viz will fail)")

        ok = not any(check["status"] == "error" for check in checks)
        payload = {
            "ok": ok,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "python": {
                "version": sys.version.split()[0],
                "executable": sys.executable,
            },
            "platform": platform.platform(),
            "dependencies": dependencies,
            "config": {
                "run_name": run_name,
                "process_name": process_name,
                "domain": domain_name,
                "schema_version": schema_version,
                "seed": seed,
                "io_format": io_format,
            },
            "checks": checks,
        }
        writer.write_json("meta/doctor.json", payload)
        writer.log("doctor complete")
