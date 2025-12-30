from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import ArtifactWriter, ensure_unique_run_name
from .registry import get_process


class BaseProcess:
    name = ""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg

    def run(self, writer: ArtifactWriter) -> None:
        raise NotImplementedError


def dispatch_process(cfg: dict[str, Any], overrides: list[str], repo_root: Path) -> Path:
    process_name = _process_name(cfg)
    run_name = cfg.get("run_name")
    if not run_name:
        raise ValueError("run_name is required")
    runs_dir = repo_root / "runs"
    unique_run_name = ensure_unique_run_name(runs_dir, str(run_name), process_name)
    if unique_run_name != run_name:
        cfg["run_name"] = unique_run_name
    writer = ArtifactWriter(repo_root=repo_root, cfg=cfg, overrides=overrides)
    writer.prepare()
    writer.log(f"dispatch process={process_name}")
    proc_cls = get_process(process_name)
    proc = proc_cls(cfg)
    proc.run(writer)
    writer.finalize()
    return writer.run_dir


def _process_name(cfg: dict[str, Any]) -> str:
    proc = cfg.get("process")
    if isinstance(proc, dict):
        name = proc.get("name")
    else:
        name = proc
    if not name:
        raise ValueError("process.name is required")
    return str(name)
