from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from synthlab.domains.wafer_particles import DOMAIN_NAME, SCHEMA_VERSION  # noqa: E402
from synthlab.framework.process import dispatch_process  # noqa: E402
from synthlab.processes._wafer_particles_io import (  # noqa: E402
    find_manifest,
    paths_from_manifest,
    read_table,
)


def _variance(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _wafer_particles_cfg(
    *,
    n_samples: int,
    noise_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = {
        "n_samples": n_samples,
        "n_particles": 400,
        "wafer_radius_mm": 100.0,
        "sample_id_prefix": "sample",
        "include_xy": False,
        "source": "synthetic",
        "label_selection": {
            "mode": "fixed",
            "labels": ["edge_sector_custom"],
            "shuffle": False,
        },
        "patterns": {
            "edge_sector_custom": {
                "name": "wafer_particles.pattern.edge_sector",
                "mode": "custom",
                "angle_center_rad": 1.25,
                "angle_width_rad": 0.3,
                "edge_width_mm": 5.0,
            }
        },
        "size_models": {
            "name": "wafer_particles.size_model.lognormal",
            "mu_log": 0.0,
            "sigma_log": 0.1,
        },
        "io": {"format": "csv"},
    }
    if noise_cfg is not None:
        cfg["noise"] = noise_cfg
    return cfg


def _make_cfg(
    *,
    run_name: str,
    seed: int,
    n_samples: int,
    noise_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "run_name": run_name,
        "seed": seed,
        "schema_version": SCHEMA_VERSION,
        "domain": {"name": DOMAIN_NAME},
        "process": {"name": "wafer_particles.process.generate"},
        "wafer_particles": _wafer_particles_cfg(n_samples=n_samples, noise_cfg=noise_cfg),
    }


def _run_generate(tmp_path: Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    run_dir = dispatch_process(cfg=cfg, overrides=[], repo_root=tmp_path)
    manifest_path = find_manifest(run_dir)
    assert manifest_path is not None
    particles_path, _ = paths_from_manifest(
        manifest_path,
        expected_schema_version=SCHEMA_VERSION,
        expected_domain=DOMAIN_NAME,
    )
    return read_table(particles_path)


def test_jitter_increases_variance(tmp_path: Path) -> None:
    base_cfg = _make_cfg(run_name="jitter_base", seed=11, n_samples=1)
    base_particles = _run_generate(tmp_path, base_cfg)

    jitter_cfg = {
        "jitter": {"enabled": True, "r_std_mm": 0.8, "theta_std_rad": 0.08},
    }
    jitter_run_cfg = _make_cfg(
        run_name="jitter_on",
        seed=11,
        n_samples=1,
        noise_cfg=jitter_cfg,
    )
    jitter_particles = _run_generate(tmp_path, jitter_run_cfg)

    base_r = [float(particle["r_mm"]) for particle in base_particles]
    base_theta = [float(particle["theta_rad"]) for particle in base_particles]
    jitter_r = [float(particle["r_mm"]) for particle in jitter_particles]
    jitter_theta = [float(particle["theta_rad"]) for particle in jitter_particles]

    assert _variance(jitter_r) > _variance(base_r)
    assert _variance(jitter_theta) > _variance(base_theta)


def test_background_adds_particles(tmp_path: Path) -> None:
    n_samples = 2
    base_cfg = _make_cfg(run_name="background_base", seed=23, n_samples=n_samples)
    base_particles = _run_generate(tmp_path, base_cfg)

    extra = 7
    background_cfg = {
        "background": {"enabled": True, "count": extra},
    }
    background_run_cfg = _make_cfg(
        run_name="background_on",
        seed=23,
        n_samples=n_samples,
        noise_cfg=background_cfg,
    )
    background_particles = _run_generate(tmp_path, background_run_cfg)

    assert len(background_particles) == len(base_particles) + extra * n_samples


def test_noise_reproducible_with_seed(tmp_path: Path) -> None:
    noise_cfg = {
        "jitter": {"enabled": True, "r_std_mm": 0.6, "theta_std_rad": 0.05},
        "background": {"enabled": True, "fraction": 0.1},
    }
    cfg_a = _make_cfg(run_name="noise_seed_a", seed=41, n_samples=1, noise_cfg=noise_cfg)
    cfg_b = _make_cfg(run_name="noise_seed_b", seed=41, n_samples=1, noise_cfg=noise_cfg)

    particles_a = _run_generate(tmp_path, cfg_a)
    particles_b = _run_generate(tmp_path, cfg_b)

    assert particles_a == particles_b
