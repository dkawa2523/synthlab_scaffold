from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.cli.main import resolve_config  # noqa: E402
from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import (  # noqa: E402
    find_manifest,
    paths_from_manifest,
    read_table,
)


def _resolve_cfg(run_name: str, *, profile_option: str | None) -> dict[str, Any]:
    overrides = {
        "process": "generate",
        "seed": 123,
        "run_name": run_name,
        "wafer_particles": {
            "n_samples": 40,
            "label_selection": {
                "mode": "fixed",
                "labels": ["ring_narrow"],
                "shuffle": False,
            },
            "io": {"format": "csv"},
        },
    }
    group_overrides = [("wafer_particles/profiles", profile_option)] if profile_option else None
    return resolve_config(overrides, repo_root=ROOT, group_overrides=group_overrides)


def _mean_n_particles(run_dir: Path) -> float:
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    _, samples_path = paths_from_manifest(
        manifest_path,
        expected_schema_version=SCHEMA_VERSION,
        expected_domain=DOMAIN_NAME,
    )
    samples = read_table(samples_path)
    counts = [int(row["n_particles"]) for row in samples]
    assert counts
    return sum(counts) / len(counts)


def _read_meta(run_dir: Path) -> dict[str, Any]:
    meta_path = run_dir / "meta" / "meta.json"
    return json.loads(meta_path.read_text(encoding="utf-8"))


def test_profile_override_changes_n_particles(tmp_path: Path) -> None:
    default_cfg = _resolve_cfg("profile_default", profile_option=None)
    default_run = dispatch_process(cfg=default_cfg, overrides=[], repo_root=tmp_path)
    default_mean = _mean_n_particles(default_run)
    default_meta = _read_meta(default_run)
    assert default_meta.get("profile_name") == "default_profile"
    assert default_meta.get("profile_hash")

    profile_cfg = _resolve_cfg("profile_etch", profile_option="etch_rie_example")
    profile_run = dispatch_process(cfg=profile_cfg, overrides=[], repo_root=tmp_path)
    profile_mean = _mean_n_particles(profile_run)
    profile_meta = _read_meta(profile_run)
    assert profile_meta.get("profile_name") == "etch_rie_example"
    assert profile_meta.get("profile_hash")

    assert profile_mean > default_mean + 50.0


def test_labeling_docs_present() -> None:
    doc14 = ROOT / "docs" / "14_LABELING_AND_GROUPS.md"
    text14 = doc14.read_text(encoding="utf-8")
    assert "14_LABELING_AND_GROUPS" in text14
    assert "Similarity group reference" in text14

    doc10 = ROOT / "docs" / "10_PROCESS_CATALOG.md"
    text10 = doc10.read_text(encoding="utf-8")
    for item in ("process=labeling_apply", "process=compose", "process=pattern_coverage"):
        assert item in text10
