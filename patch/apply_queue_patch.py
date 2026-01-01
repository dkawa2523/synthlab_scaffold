#!/usr/bin/env python3
"""Apply a queue patch JSON to work/queue.json safely.

- Adds new tasks by `id` if not present.
- Does not delete or overwrite existing tasks with same id.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python patch/apply_queue_patch.py patch/queue_patch_XXXX.json")
        return 2
    patch_path = Path(sys.argv[1])
    repo_root = Path(__file__).resolve().parents[1]
    queue_path = repo_root / "work" / "queue.json"

    if not queue_path.exists():
        raise SystemExit(f"Missing {queue_path}. Are you in the repo root?")

    patch = json.loads(patch_path.read_text(encoding="utf-8"))
    new_items = patch.get("items", patch)

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    if isinstance(queue, dict) and "items" in queue:
        items = queue["items"]
        wrapper = True
    else:
        items = queue
        wrapper = False

    existing_ids = {it.get("id") for it in items if isinstance(it, dict)}
    added = 0
    for it in new_items:
        tid = it.get("id")
        if tid in existing_ids:
            continue
        items.append(it)
        existing_ids.add(tid)
        added += 1

    # sort by id if possible (TXXXX numeric)
    def sort_key(it):
        tid = str(it.get("id",""))
        import re
        m = re.match(r"T(\d+)", tid)
        return int(m.group(1)) if m else 10**9

    items.sort(key=sort_key)

    if wrapper:
        queue["items"] = items
        queue_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        queue_path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Applied patch: added {added} tasks.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
