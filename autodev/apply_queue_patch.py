#!/usr/bin/env python3
"""
Apply a queue patch (list of task entries) to work/queue.json without destroying existing statuses.

Usage:
  python autodev/apply_queue_patch.py patch/queue_patch_T0104_T0108.json
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    if len(sys.argv) < 2:
        print("ERROR: patch json path is required.", file=sys.stderr)
        print("Usage: python autodev/apply_queue_patch.py patch/queue_patch_T0104_T0108.json", file=sys.stderr)
        sys.exit(2)

    patch_path = Path(sys.argv[1])
    repo_root = Path(".")
    queue_path = repo_root / "work" / "queue.json"

    if not patch_path.exists():
        print(f"ERROR: patch not found: {patch_path}", file=sys.stderr)
        sys.exit(2)
    if not queue_path.exists():
        print(f"ERROR: queue not found: {queue_path} (run from repo root)", file=sys.stderr)
        sys.exit(2)

    queue = load_json(queue_path)
    patch = load_json(patch_path)

    if not isinstance(queue, list) or not isinstance(patch, list):
        print("ERROR: queue.json and patch must be JSON arrays.", file=sys.stderr)
        sys.exit(2)

    existing_ids = {t.get("id") for t in queue if isinstance(t, dict)}
    added = 0
    skipped = 0
    for item in patch:
        if not isinstance(item, dict) or "id" not in item:
            print("WARNING: invalid patch entry (skipped)", file=sys.stderr)
            skipped += 1
            continue
        if item["id"] in existing_ids:
            print(f"INFO: already exists, skip: {item['id']}", file=sys.stderr)
            skipped += 1
            continue
        queue.append(item)
        existing_ids.add(item["id"])
        added += 1

    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Applied patch: added={added}, skipped={skipped}")
    print("Next:")
    print("  python autodev/run_loop.py --loop")

if __name__ == "__main__":
    main()
