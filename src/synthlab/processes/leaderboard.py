from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import resolve_path


@register_process("wafer_particles.process.leaderboard")
class LeaderboardProcess(BaseProcess):
    name = "wafer_particles.process.leaderboard"

    def run(self, writer) -> None:
        writer.log("leaderboard start")
        lb_cfg = _resolve_leaderboard_cfg(self.cfg)
        inputs_cfg = _read_mapping(lb_cfg.get("inputs"), "wafer_particles.leaderboard.inputs")

        run_dirs = _resolve_run_dirs(inputs_cfg, repo_root=writer.repo_root)
        metrics_path = str(lb_cfg.get("metrics_path", "metrics/eval_summary.json"))
        metric_key = lb_cfg.get("metric_key") or lb_cfg.get("primary_metric")
        sort_order = str(lb_cfg.get("sort_order", "desc")).lower()
        compare_cfg = _read_mapping(lb_cfg.get("compare"), "wafer_particles.leaderboard.compare", required=False)

        rows = [
            _load_row(run_dir, metrics_path, metric_key)
            for run_dir in run_dirs
        ]
        _enforce_comparability(rows, compare_cfg)

        rows_sorted = _sort_rows(rows, metric_key, sort_order)
        _write_csv(writer.run_dir / "leaderboard.csv", rows_sorted, metric_key)
        (writer.run_dir / "leaderboard.html").write_text(
            "leaderboard html is not generated in this scaffold\n",
            encoding="utf-8",
        )
        writer.write_json(
            "metrics/leaderboard.json",
            {
                "metric_key": metric_key,
                "metrics_path": metrics_path,
                "sort_order": sort_order,
                "compare": compare_cfg,
                "runs": rows_sorted,
            },
        )
        writer.log("leaderboard complete")


def _resolve_leaderboard_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    lb_cfg = wp_cfg.get("leaderboard")
    if not isinstance(lb_cfg, Mapping):
        raise ValueError("wafer_particles.leaderboard config is required")
    return dict(lb_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _resolve_run_dirs(inputs_cfg: Mapping[str, Any], *, repo_root: Path) -> list[Path]:
    run_dirs: list[Path] = []
    run_dirs_cfg = inputs_cfg.get("run_dirs") or []
    if not isinstance(run_dirs_cfg, list):
        raise ValueError("wafer_particles.leaderboard.inputs.run_dirs must be a list")
    for item in run_dirs_cfg:
        run_dirs.append(resolve_path(item, repo_root))

    run_names = inputs_cfg.get("run_names") or []
    if not isinstance(run_names, list):
        raise ValueError("wafer_particles.leaderboard.inputs.run_names must be a list")
    process_name = str(inputs_cfg.get("process_name", "wafer_particles.process.eval"))
    for run_name in run_names:
        run_dirs.append(repo_root / "runs" / str(run_name) / process_name)

    if not run_dirs:
        raise ValueError("leaderboard requires run_dirs or run_names")

    unique: list[Path] = []
    seen: set[str] = set()
    for run_dir in run_dirs:
        key = str(run_dir)
        if key in seen:
            continue
        if not run_dir.exists():
            raise ValueError(f"run_dir not found: {run_dir}")
        seen.add(key)
        unique.append(run_dir)
    return unique


def _load_row(run_dir: Path, metrics_path: str, metric_key: str | None) -> dict[str, Any]:
    metrics_file = run_dir / metrics_path
    if not metrics_file.exists():
        raise ValueError(f"metrics file not found: {metrics_file}")
    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
    if not isinstance(metrics, Mapping):
        raise ValueError(f"metrics file must be a mapping: {metrics_file}")

    meta = _read_json_if_exists(run_dir / "meta" / "meta.json")
    run_name, process_name = _infer_run_info(run_dir, meta)

    metric_value = _extract_metric(metrics, metric_key) if metric_key else None

    return {
        "run_name": run_name,
        "process_name": process_name,
        "run_dir": str(run_dir),
        "created_at": meta.get("created_at"),
        "config_hash": meta.get("config_hash"),
        "git_sha": meta.get("git_sha"),
        "schema_version": metrics.get("schema_version") or meta.get("schema_version"),
        "dataset_id": metrics.get("dataset_id"),
        "seed_policy": metrics.get("seed_policy"),
        "eval_config_hash": metrics.get("eval_config_hash"),
        "metric_key": metric_key,
        "metric_value": metric_value,
    }


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        return {}
    return dict(data)


def _infer_run_info(run_dir: Path, meta: Mapping[str, Any]) -> tuple[str, str]:
    run_name = meta.get("run_name")
    process_name = meta.get("process_name")
    if not run_name:
        run_name = run_dir.parent.name
    if not process_name:
        process_name = run_dir.name
    return str(run_name), str(process_name)


def _extract_metric(metrics: Mapping[str, Any], metric_key: str) -> Any:
    cur: Any = metrics
    for part in metric_key.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _enforce_comparability(rows: list[dict[str, Any]], compare_cfg: Mapping[str, Any]) -> None:
    if not rows:
        raise ValueError("leaderboard requires at least one run")
    if _flag(compare_cfg, "require_same_schema_version", True):
        _require_same(rows, "schema_version", "schema_version")
    if _flag(compare_cfg, "require_same_dataset_id", True):
        _require_same(rows, "dataset_id", "dataset_id")
    if _flag(compare_cfg, "require_same_seed_policy", True):
        _require_same(rows, "seed_policy", "seed_policy")
    if _flag(compare_cfg, "require_same_eval_config_hash", True):
        _require_same(rows, "eval_config_hash", "eval_config_hash")


def _flag(compare_cfg: Mapping[str, Any], key: str, default: bool) -> bool:
    if key in compare_cfg:
        return bool(compare_cfg.get(key))
    return default


def _require_same(rows: list[dict[str, Any]], key: str, label: str) -> None:
    values: dict[str, Any] = {}
    for row in rows:
        values[str(row.get("run_name"))] = row.get(key)
    unique = {value for value in values.values()}
    if None in unique or len(unique) != 1:
        details = ", ".join(f"{name}={values[name]}" for name in sorted(values))
        raise ValueError(f"leaderboard compare failed for {label}: {details}")


def _sort_rows(rows: list[dict[str, Any]], metric_key: str | None, sort_order: str) -> list[dict[str, Any]]:
    if not metric_key:
        return rows
    reverse = sort_order != "asc"

    def _sort_value(value: Any) -> float:
        if value is None:
            return float("-inf") if reverse else float("inf")
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf") if reverse else float("inf")

    return sorted(rows, key=lambda row: _sort_value(row.get("metric_value")), reverse=reverse)


def _write_csv(path: Path, rows: list[dict[str, Any]], metric_key: str | None) -> None:
    fieldnames = [
        "rank",
        "run_name",
        "process_name",
        "metric_key",
        "metric_value",
        "dataset_id",
        "schema_version",
        "eval_config_hash",
        "seed_policy",
        "config_hash",
        "git_sha",
        "created_at",
        "run_dir",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "rank": idx,
                    "run_name": row.get("run_name"),
                    "process_name": row.get("process_name"),
                    "metric_key": metric_key,
                    "metric_value": row.get("metric_value"),
                    "dataset_id": row.get("dataset_id"),
                    "schema_version": row.get("schema_version"),
                    "eval_config_hash": row.get("eval_config_hash"),
                    "seed_policy": row.get("seed_policy"),
                    "config_hash": row.get("config_hash"),
                    "git_sha": row.get("git_sha"),
                    "created_at": row.get("created_at"),
                    "run_dir": row.get("run_dir"),
                }
            )
