from __future__ import annotations

import copy
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml


def canonicalize_config_for_hash(cfg: dict[str, Any]) -> dict[str, Any]:
    canonical = copy.deepcopy(cfg)
    if isinstance(canonical, dict):
        canonical.pop("hydra", None)
        canonical.pop("run_name", None)
    return canonical


def compute_config_hash(cfg: dict[str, Any]) -> str:
    canonical = canonicalize_config_for_hash(cfg)
    dumped = yaml.safe_dump(canonical, sort_keys=True)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:12]


def ensure_unique_run_name(runs_dir: Path, run_name: str, process_name: str) -> str:
    candidate = run_name
    suffix = 1
    while (runs_dir / candidate / process_name).exists():
        candidate = f"{run_name}_{suffix}"
        suffix += 1
    return candidate


def _git_sha(repo_root: Path) -> Optional[str]:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if p.returncode != 0:
        return None
    return p.stdout.strip() or None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump_yaml(path: Path, cfg: dict[str, Any]) -> None:
    text = yaml.safe_dump(cfg, sort_keys=True, allow_unicode=False)
    path.write_text(text, encoding="utf-8")


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    path.write_text(text + "\n", encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"yaml must be a mapping: {path}")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"json must be a mapping: {path}")
    return data


def _safe_rel_path(run_dir: Path, rel_path: str) -> Path:
    rel = Path(rel_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"rel_path must be within run dir: {rel_path}")
    return run_dir / rel


@dataclass
class ArtifactWriter:
    repo_root: Path
    cfg: dict[str, Any]
    overrides: list[str]

    def __post_init__(self) -> None:
        self.process_name = _process_name(self.cfg)
        self.run_name = str(self.cfg.get("run_name") or "")
        self.run_dir = self.repo_root / "runs" / self.run_name / self.process_name
        self.created_at = _iso_now()
        self.config_hash = compute_config_hash(self.cfg)
        self._log_path = self.run_dir / "logs" / "console.log"

    def prepare(self) -> None:
        self._create_dirs()
        self._write_config()
        self._write_meta()
        self._write_readme()
        if not self._log_path.exists():
            self._log_path.write_text("", encoding="utf-8")

    def log(self, message: str) -> None:
        line = f"[{_iso_now()}] {message}"
        print(line, flush=True)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def write_json(self, rel_path: str, payload: dict[str, Any]) -> None:
        path = _safe_rel_path(self.run_dir, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _dump_json(path, payload)

    def finalize(self) -> None:
        self.log("process completed")

    def _create_dirs(self) -> None:
        for rel in [
            "config",
            "meta",
            "data",
            "metrics",
            "plots",
            "logs",
        ]:
            (self.run_dir / rel).mkdir(parents=True, exist_ok=True)

    def _write_config(self) -> None:
        _dump_yaml(self.run_dir / "config" / "resolved.yaml", self.cfg)
        overrides_text = "\n".join(self.overrides) + ("\n" if self.overrides else "")
        (self.run_dir / "config" / "overrides.txt").write_text(overrides_text, encoding="utf-8")

    def _write_meta(self) -> None:
        profile_name, profile_hash = _profile_meta(self.cfg)
        meta = {
            "run_name": self.run_name,
            "process_name": self.process_name,
            "created_at": self.created_at,
            "seed": self.cfg.get("seed"),
            "git_sha": _git_sha(self.repo_root),
            "config_hash": self.config_hash,
            "domain": _domain_name(self.cfg),
            "schema_version": self.cfg.get("schema_version"),
            "notes": self.cfg.get("notes"),
            "profile_name": profile_name,
            "profile_hash": profile_hash,
            "env": {
                "python": sys.version.split()[0],
                "executable": sys.executable,
                "platform": platform.platform(),
            },
        }
        _dump_json(self.run_dir / "meta" / "meta.json", meta)

    def _write_readme(self) -> None:
        lines = [
            "# Run Summary",
            "",
            f"- run_name: {self.run_name}",
            f"- process: {self.process_name}",
            f"- created_at: {self.created_at}",
        ]
        (self.run_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class ArtifactReader:
    run_dir: Path

    def read_config(self) -> dict[str, Any]:
        return _read_yaml(self.run_dir / "config" / "resolved.yaml")

    def read_overrides(self) -> list[str]:
        path = self.run_dir / "config" / "overrides.txt"
        if not path.exists():
            return []
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read_meta(self) -> dict[str, Any]:
        return _read_json(self.run_dir / "meta" / "meta.json")

    def compute_config_hash(self) -> str:
        return compute_config_hash(self.read_config())


def _process_name(cfg: dict[str, Any]) -> str:
    proc = cfg.get("process")
    if isinstance(proc, dict):
        name = proc.get("name")
    else:
        name = proc
    if not name:
        raise ValueError("process.name is required")
    return str(name)


def _domain_name(cfg: dict[str, Any]) -> Any:
    domain = cfg.get("domain")
    if isinstance(domain, dict):
        return domain.get("name")
    return domain


def _profile_meta(cfg: dict[str, Any]) -> tuple[str | None, str | None]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, dict):
        return None, None
    profile_cfg = wp_cfg.get("profiles")
    if not isinstance(profile_cfg, dict):
        return None, None
    name = profile_cfg.get("name")
    profile_hash = compute_config_hash(dict(profile_cfg))
    return (str(name) if name is not None else None, profile_hash)
