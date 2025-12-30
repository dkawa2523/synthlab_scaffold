from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from synthlab.framework.registry import register_model


@register_model("wafer_particles.model.noop")
def noop_model(
    cfg: Mapping[str, Any],
    inputs: Mapping[str, Any],
    *,
    stage: str,
    seed: int,
    model_dir: Path,
    preds_dir: Path,
) -> dict[str, Any]:
    model_dir.mkdir(parents=True, exist_ok=True)
    preds_dir.mkdir(parents=True, exist_ok=True)
    if stage == "train":
        (model_dir / "noop.txt").write_text("noop model placeholder\n", encoding="utf-8")
    return {
        "model_info": {
            "name": "wafer_particles.model.noop",
            "stage": stage,
            "seed": seed,
        },
        "metrics": {
            "status": "noop",
        },
        "preds": [],
    }
