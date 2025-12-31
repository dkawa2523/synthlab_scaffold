from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402

TAXONOMY_PATH = ROOT / "conf" / "wafer_particles" / "labels" / "taxonomy_v1.yaml"


def _load_taxonomy() -> dict[str, Any]:
    data = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("taxonomy_v1.yaml must be a mapping")
    return data


def _require_rules(entry: dict[str, Any], name: str) -> list[str]:
    rules = entry.get("expected_rules")
    if not isinstance(rules, list) or not rules:
        raise AssertionError(f"expected_rules missing for {name}")
    return [str(rule) for rule in rules]


def _expected_rules_for_label(taxonomy: dict[str, Any], label: str) -> list[str]:
    labels = taxonomy.get("labels")
    if not isinstance(labels, list):
        return []
    for entry in labels:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == label:
            return [str(rule) for rule in entry.get("expected_rules", [])]
        variants = entry.get("variants") or []
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            if variant.get("name") == label:
                return [str(rule) for rule in variant.get("expected_rules", [])]
    return []


def _wafer_particles_cfg(taxonomy: dict[str, Any]) -> dict[str, Any]:
    return {
        "n_samples": 2,
        "n_particles": 25,
        "wafer_radius_mm": 10.0,
        "sample_id_prefix": "sample",
        "include_xy": False,
        "source": "synthetic",
        "labels": taxonomy,
        "label_selection": {
            "mode": "fixed",
            "labels": ["random_uniform"],
            "shuffle": False,
        },
        "patterns": {
            "random_uniform": {
                "name": "wafer_particles.pattern.random_uniform",
            }
        },
        "size_models": {
            "name": "wafer_particles.size_model.lognormal",
            "mu_log": 0.0,
            "sigma_log": 0.1,
        },
        "io": {"format": "csv"},
        "qc": {
            "input": {
                "run_name": None,
                "process_name": "wafer_particles.process.generate",
                "run_dir": None,
                "manifest_path": None,
                "particles_path": None,
                "samples_path": None,
            },
            "bins": {
                "r": {"start": 0.0, "stop": 10.0, "count": 5},
                "theta": {"start": 0.0, "stop": 6.283185307179586, "count": 6},
            },
            "quantiles": [0.5],
            "rules": {},
        },
    }


def _make_cfg(process_name: str, run_name: str, seed: int, taxonomy: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": process_name},
        "wafer_particles": _wafer_particles_cfg(taxonomy),
    }


def test_taxonomy_expected_rules_no_todo() -> None:
    taxonomy = _load_taxonomy()
    labels = taxonomy.get("labels")
    assert isinstance(labels, list) and labels
    for entry in labels:
        assert isinstance(entry, dict)
        name = str(entry.get("name") or "")
        assert name
        for rule in _require_rules(entry, name):
            assert "TODO" not in rule
        variants = entry.get("variants") or []
        if not variants:
            continue
        assert isinstance(variants, list)
        for variant in variants:
            assert isinstance(variant, dict)
            variant_name = str(variant.get("name") or "")
            assert variant_name
            for rule in _require_rules(variant, variant_name):
                assert "TODO" not in rule


def test_qc_metrics_include_expected_rules(tmp_path: Path) -> None:
    taxonomy = _load_taxonomy()
    gen_cfg = _make_cfg("wafer_particles.process.generate", "t0107_gen", seed=101, taxonomy=taxonomy)
    gen_run = dispatch_process(cfg=gen_cfg, overrides=[], repo_root=tmp_path)

    qc_cfg = _make_cfg("wafer_particles.process.qc", "t0107_qc", seed=101, taxonomy=taxonomy)
    qc_cfg["wafer_particles"]["qc"]["input"]["run_dir"] = str(gen_run)
    qc_run = dispatch_process(cfg=qc_cfg, overrides=[], repo_root=tmp_path)

    payload = json.loads((qc_run / "metrics" / "qc.json").read_text(encoding="utf-8"))
    label_info = payload["labels"]["random_uniform"]
    expected_rules = _expected_rules_for_label(taxonomy, "random_uniform")
    assert label_info["expected_rules"] == expected_rules
    assert label_info["expected_rules"]
