\
"""
autodev/verifiers.py (v2.2)

- タスクごとに "機械的に判定可能" な Verification を提供する。
- 特に T0003 (artifact contract) は、よく詰まるので専用の厳密検証を持つ。

Verification は以下の方針:
- 失敗時に Codex に渡せる「短いsummary」を返す
- 同じタスクを何度も回す場合でも、最新の runs/ を自動で追跡する
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml


@dataclasses.dataclass
class VerificationResult:
    ok: bool
    summary: str = ""


def _run(cmd: list[str], cwd: Path, out_log: Path) -> int:
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    out_log.write_text(p.stdout or "", encoding="utf-8")
    return p.returncode


def _latest_artifact_dir(runs_dir: Path, process_name: str) -> Optional[Path]:
    """
    runs/<run_name>/<process_name> を探索して最終更新の新しいものを返す。
    """
    if not runs_dir.exists():
        return None
    candidates = []
    for run_name_dir in runs_dir.iterdir():
        if not run_name_dir.is_dir():
            continue
        p = run_name_dir / process_name
        if p.is_dir():
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _canonicalize_for_hash(cfg: dict) -> dict:
    """
    config_hash 用 canonicalization。

    目的: run_name や hydra ランタイムなど「実行ごとに変わる」値で hash が変わらないようにする。
    """
    # deep copy-ish (simple)
    import copy
    x = copy.deepcopy(cfg) if isinstance(cfg, dict) else cfg
    if isinstance(x, dict):
        x.pop("hydra", None)
        x.pop("run_name", None)
    return x


def _config_hash_from_resolved_yaml(resolved_yaml_path: Path) -> str:
    cfg = _read_yaml(resolved_yaml_path)
    can = _canonicalize_for_hash(cfg)
    # stable dump
    dumped = yaml.safe_dump(can, sort_keys=True)
    h = hashlib.sha256(dumped.encode("utf-8")).hexdigest()
    return h[:12]


def verify_task(task_id: str, repo_root: Path, cfg: dict, out_log: Path) -> VerificationResult:
    if task_id == "T0003":
        return _verify_T0003(repo_root, cfg, out_log)
    # default: try to run doctor and ensure it exits 0
    # (P0 tasks should be validated by custom verifiers; fallback keeps loop alive)
    rc = _run(["python", "-m", "synthlab.cli.main", "process=doctor", "seed=1"], cwd=repo_root, out_log=out_log)
    if rc != 0:
        return VerificationResult(False, f"doctor failed (rc={rc}). Check {out_log}")
    return VerificationResult(True, "doctor ok")


def _verify_T0003(repo_root: Path, cfg: dict, out_log: Path) -> VerificationResult:
    """
    T0003: Artifact契約の検証
    - doctor を2回実行して artifact を作る
    - 必須ファイルの存在
    - meta.json の必須キー
    - config_hash が run_name/hydra に依存せず安定している（2回で一致）
    - meta.config_hash が canonical hash と一致する
    """
    runs_dir = repo_root / cfg.get("paths", {}).get("runs_dir", "runs")

    # run 1
    log1 = out_log.parent / (out_log.stem + "_doctor1.log")
    rc1 = _run(["python", "-m", "synthlab.cli.main", "process=doctor", "seed=1"], cwd=repo_root, out_log=log1)
    if rc1 != 0:
        out_log.write_text(log1.read_text(encoding="utf-8"), encoding="utf-8")
        return VerificationResult(False, f"T0003: doctor run1 failed (rc={rc1}). See {log1}")

    art1 = _latest_artifact_dir(runs_dir, "doctor")
    if art1 is None:
        return VerificationResult(False, f"T0003: no artifact found under {runs_dir}/<run_name>/doctor")

    # run 2
    log2 = out_log.parent / (out_log.stem + "_doctor2.log")
    rc2 = _run(["python", "-m", "synthlab.cli.main", "process=doctor", "seed=1"], cwd=repo_root, out_log=log2)
    if rc2 != 0:
        out_log.write_text(log2.read_text(encoding="utf-8"), encoding="utf-8")
        return VerificationResult(False, f"T0003: doctor run2 failed (rc={rc2}). See {log2}")

    art2 = _latest_artifact_dir(runs_dir, "doctor")
    if art2 is None:
        return VerificationResult(False, f"T0003: no artifact found for run2 under {runs_dir}")
    # if art2 equals art1 (very fast runs with same dir), still proceed; compare meta inside

    def check_artifact(art: Path) -> Tuple[bool, str, dict]:
        required = [
            art / "config" / "resolved.yaml",
            art / "config" / "overrides.txt",
            art / "meta" / "meta.json",
        ]
        missing = [p for p in required if not p.exists()]
        if missing:
            return False, f"Missing required files: " + ", ".join(str(m) for m in missing), {}
        meta = json.loads((art / "meta" / "meta.json").read_text(encoding="utf-8"))
        # minimal required keys
        needed_keys = ["run_name", "process_name", "created_at", "seed", "config_hash"]
        miss_k = [k for k in needed_keys if k not in meta]
        if miss_k:
            return False, f"meta.json missing keys: {miss_k}", meta
        return True, "ok", meta

    ok1, msg1, meta1 = check_artifact(art1)
    ok2, msg2, meta2 = check_artifact(art2)

    # Combine logs for reference
    out_log.write_text(
        f"artifact1={art1}\n{msg1}\n\nartifact2={art2}\n{msg2}\n\n"
        f"doctor1_log={log1}\n----\n{log1.read_text(encoding='utf-8')}\n\n"
        f"doctor2_log={log2}\n----\n{log2.read_text(encoding='utf-8')}\n",
        encoding="utf-8"
    )

    if not ok1:
        return VerificationResult(False, f"T0003: artifact1 invalid: {msg1}\nartifact1={art1}")
    if not ok2:
        return VerificationResult(False, f"T0003: artifact2 invalid: {msg2}\nartifact2={art2}")

    # config_hash stability check
    h1 = str(meta1.get("config_hash"))
    h2 = str(meta2.get("config_hash"))
    if h1 != h2:
        return VerificationResult(
            False,
            "T0003: config_hash is not stable across identical runs. "
            f"config_hash1={h1}, config_hash2={h2}. "
            "Fix: compute config_hash from canonicalized resolved config (exclude run_name/hydra)."
        )

    # meta config_hash should match canonical hash from resolved.yaml
    calc1 = _config_hash_from_resolved_yaml(art1 / "config" / "resolved.yaml")
    if h1 != calc1:
        return VerificationResult(
            False,
            "T0003: meta.config_hash does not match canonical hash of config/resolved.yaml. "
            f"meta={h1}, computed={calc1}. "
            "Fix: align hash algorithm with docs/04 (exclude run_name/hydra; stable yaml dump)."
        )

    return VerificationResult(True, "T0003 ok")
