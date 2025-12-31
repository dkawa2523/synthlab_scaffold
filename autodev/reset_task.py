\
#!/usr/bin/env python3
"""
autodev/reset_task.py
- queue.json の task status を指定状態へ戻す（blocked解除など）
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("--to", default="todo", choices=["todo", "doing", "done", "blocked"])
    ap.add_argument("--clear-attempts", action="store_true")
    ap.add_argument("--clear-blocked-reason", action="store_true")
    ap.add_argument("--clear-last-failure", action="store_true")
    args = ap.parse_args()

    repo = Path.cwd()
    cfg = load_yaml(repo / "autodev/config.yaml")
    queue_path = repo / cfg["paths"]["queue_file"]
    queue = load_json(queue_path)

    found = False
    for q in queue:
        if q["id"] == args.task_id:
            q["status"] = args.to
            if args.clear_blocked_reason:
                q.pop("blocked_reason", None)
            if args.clear_attempts:
                q.pop("attempts", None)
            if args.clear_last_failure:
                q.pop("last_result", None)
            found = True

    if not found:
        print(f"Task {args.task_id} not found in {queue_path}")
        return 1

    save_json(queue_path, queue)
    print(f"Reset {args.task_id} -> {args.to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
