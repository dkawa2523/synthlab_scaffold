\
#!/usr/bin/env python3
"""
autodev/show_queue.py
- work/queue.json を見やすく表示する
"""
from __future__ import annotations

import json
from pathlib import Path
import yaml


def main() -> int:
    repo = Path.cwd()
    cfg = yaml.safe_load((repo / "autodev/config.yaml").read_text(encoding="utf-8"))
    queue = json.loads((repo / cfg["paths"]["queue_file"]).read_text(encoding="utf-8"))

    # simple table
    rows = []
    for q in queue:
        rows.append((q["id"], q.get("priority"), q.get("status"), q.get("title")))
    # sort by priority then id
    pr_order = {"P0": 0, "P1": 1, "P2": 2, None: 9}
    rows.sort(key=lambda x: (pr_order.get(x[1], 9), x[0]))

    for r in rows:
        print(f"{r[0]} [{r[1]}] {r[2]:7s} - {r[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
