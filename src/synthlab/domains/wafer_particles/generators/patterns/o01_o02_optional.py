from __future__ import annotations

import math
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, cartesian_to_polar_norm, mm_to_norm, sample_uniform_disk_xy


@register_pattern("wafer_particles.pattern.O01_ReticleRepeat")
class O01ReticleRepeat(PatternBase):
    pattern_id = "O01_ReticleRepeat"
    tags = ("grid", "reticle")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        pitch_norm = _resolve_pitch_norm(params, ctx, default_ratio=0.2)
        tile_ratio = _resolve_tile_ratio(params, default_ratio=0.75)
        phase_x = _resolve_phase_norm(params, ctx, pitch_norm, rng, axis="x")
        phase_y = _resolve_phase_norm(params, ctx, pitch_norm, rng, axis="y")
        return _sample_grid(
            ctx,
            rng,
            pitch_norm=pitch_norm,
            tile_ratio=tile_ratio,
            phase_x=phase_x,
            phase_y=phase_y,
            checkerboard=False,
        )


@register_pattern("wafer_particles.pattern.O02_Checkerboard")
class O02Checkerboard(PatternBase):
    pattern_id = "O02_Checkerboard"
    tags = ("grid", "checkerboard")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        pitch_norm = _resolve_pitch_norm(params, ctx, default_ratio=0.2)
        tile_ratio = _resolve_tile_ratio(params, default_ratio=0.9)
        phase_x = _resolve_phase_norm(params, ctx, pitch_norm, rng, axis="x")
        phase_y = _resolve_phase_norm(params, ctx, pitch_norm, rng, axis="y")
        return _sample_grid(
            ctx,
            rng,
            pitch_norm=pitch_norm,
            tile_ratio=tile_ratio,
            phase_x=phase_x,
            phase_y=phase_y,
            checkerboard=True,
        )


def _resolve_pitch_norm(cfg: Mapping[str, Any], ctx: PatternContext, *, default_ratio: float) -> float:
    if "pitch_norm" in cfg:
        pitch_norm = float(cfg["pitch_norm"])
    elif "pitch_mm" in cfg:
        pitch_norm = mm_to_norm(float(cfg["pitch_mm"]), ctx.wafer_radius_mm)
    else:
        pitch_norm = float(cfg.get("pitch_ratio", default_ratio))
    if pitch_norm <= 0:
        raise ValueError("pitch_norm must be positive")
    return pitch_norm


def _resolve_tile_ratio(cfg: Mapping[str, Any], *, default_ratio: float) -> float:
    value = cfg.get("tile_ratio", default_ratio)
    tile_ratio = float(value)
    if tile_ratio <= 0 or tile_ratio > 1.0:
        raise ValueError("tile_ratio must be in (0, 1]")
    return tile_ratio


def _resolve_phase_norm(
    cfg: Mapping[str, Any],
    ctx: PatternContext,
    pitch_norm: float,
    rng: Any,
    *,
    axis: str,
) -> float:
    key_norm = f"phase_{axis}_norm"
    key_mm = f"phase_{axis}_mm"
    key_ratio = f"phase_{axis}_ratio"
    if key_norm in cfg:
        return float(cfg[key_norm])
    if key_mm in cfg:
        return mm_to_norm(float(cfg[key_mm]), ctx.wafer_radius_mm)
    if key_ratio in cfg:
        return float(cfg[key_ratio]) * pitch_norm
    mode = str(cfg.get("phase_mode", cfg.get("phase_offset_mode", ""))).lower()
    if mode in {"random", "random_phase", "random_offset"} or bool(cfg.get("phase_random", False)):
        return (rng.random() - 0.5) * pitch_norm
    return 0.0


def _sample_grid(
    ctx: PatternContext,
    rng: Any,
    *,
    pitch_norm: float,
    tile_ratio: float,
    phase_x: float,
    phase_y: float,
    checkerboard: bool,
) -> list[dict[str, Any]]:
    tile_size = pitch_norm * tile_ratio
    margin = (pitch_norm - tile_size) * 0.5
    particles: list[dict[str, Any]] = []
    attempts = 0
    max_attempts = max(1000, ctx.n_particles * 200)
    while len(particles) < ctx.n_particles and attempts < max_attempts:
        attempts += 1
        x_norm, y_norm = sample_uniform_disk_xy(rng)
        if _grid_mask(
            x_norm,
            y_norm,
            pitch_norm=pitch_norm,
            margin=margin,
            phase_x=phase_x,
            phase_y=phase_y,
            checkerboard=checkerboard,
        ):
            r_norm, theta_rad = cartesian_to_polar_norm(x_norm, y_norm)
            particles.append(build_particle(r_norm, theta_rad))
    while len(particles) < ctx.n_particles:
        x_norm, y_norm = sample_uniform_disk_xy(rng)
        r_norm, theta_rad = cartesian_to_polar_norm(x_norm, y_norm)
        particles.append(build_particle(r_norm, theta_rad))
    return particles


def _grid_mask(
    x_norm: float,
    y_norm: float,
    *,
    pitch_norm: float,
    margin: float,
    phase_x: float,
    phase_y: float,
    checkerboard: bool,
) -> bool:
    idx_x = math.floor((x_norm + phase_x) / pitch_norm)
    idx_y = math.floor((y_norm + phase_y) / pitch_norm)
    if checkerboard and (idx_x + idx_y) % 2 != 0:
        return False
    local_x = (x_norm + phase_x) - idx_x * pitch_norm
    local_y = (y_norm + phase_y) - idx_y * pitch_norm
    if local_x < margin or local_x > pitch_norm - margin:
        return False
    if local_y < margin or local_y > pitch_norm - margin:
        return False
    return True
