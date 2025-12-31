from __future__ import annotations

from math import atan2, cos, hypot, radians, sin, tau
from typing import Any, Iterable, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm, resolve_width_norm
from .geometry import sample_line_segment


@register_pattern("wafer_particles.pattern.C06_RadialLines")
class C06RadialLines(PatternBase):
    pattern_id = "C06_RadialLines"
    tags = ("line", "radial")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        angles_rad = _resolve_angles_rad(params)
        angular_jitter_rad = _resolve_jitter_rad(params)
        r_min_norm, r_max_norm = _resolve_radius_range(params, ctx)
        sigma_perp_norm = _resolve_sigma_perp_norm(params, ctx)

        n_lines = len(angles_rad)
        counts = _allocate_counts(ctx.n_particles, n_lines)
        particles: list[dict[str, Any]] = []
        for angle, count in zip(angles_rad, counts):
            if count <= 0:
                continue
            angle = angle + (rng.random() - 0.5) * 2.0 * angular_jitter_rad
            points = _sample_radial_segment(
                rng,
                count,
                angle=angle,
                r_min=r_min_norm,
                r_max=r_max_norm,
                sigma_perp=sigma_perp_norm,
            )
            particles.extend(build_particle(r_norm, theta_rad) for r_norm, theta_rad in points)
        return particles


@register_pattern("wafer_particles.pattern.C07_StraightLine")
class C07StraightLine(PatternBase):
    pattern_id = "C07_StraightLine"
    tags = ("line", "straight")

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        angle_rad = _resolve_angle_rad(params)
        segment_half_length_norm = _resolve_segment_half_length_norm(params, ctx)
        width_norm = resolve_width_norm(params, ctx, default_ratio=0.02)
        offset_norm = _resolve_offset_norm(params, ctx)

        if segment_half_length_norm <= 0:
            raise ValueError("segment_half_length_norm must be positive")
        if width_norm <= 0:
            raise ValueError("width_norm must be positive")

        perp_x = -sin(angle_rad)
        perp_y = cos(angle_rad)
        center_x = perp_x * offset_norm
        center_y = perp_y * offset_norm
        length_norm = segment_half_length_norm * 2.0

        points = sample_line_segment(
            rng,
            ctx.n_particles,
            center_x=center_x,
            center_y=center_y,
            angle_rad=angle_rad,
            length_norm=length_norm,
            width_norm=width_norm,
        )
        return [build_particle(r_norm, theta_rad) for r_norm, theta_rad in points]


def _resolve_angles_rad(cfg: Mapping[str, Any]) -> list[float]:
    if "angles_rad" in cfg:
        return [float(value) for value in _ensure_iterable(cfg["angles_rad"])]
    if "angles_deg" in cfg:
        return [radians(float(value)) for value in _ensure_iterable(cfg["angles_deg"])]
    n_lines = int(cfg.get("n_lines", 6))
    if n_lines <= 0:
        raise ValueError("n_lines must be positive")
    offset = _resolve_angle_offset_rad(cfg)
    return [offset + tau * idx / n_lines for idx in range(n_lines)]


def _resolve_angle_offset_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_offset_rad" in cfg:
        return float(cfg["angle_offset_rad"])
    if "angle_offset_deg" in cfg:
        return radians(float(cfg["angle_offset_deg"]))
    return 0.0


def _resolve_jitter_rad(cfg: Mapping[str, Any]) -> float:
    if "angular_jitter_rad" in cfg:
        return float(cfg["angular_jitter_rad"])
    if "angular_jitter_deg" in cfg:
        return radians(float(cfg["angular_jitter_deg"]))
    return radians(1.5)


def _resolve_radius_range(cfg: Mapping[str, Any], ctx: PatternContext) -> tuple[float, float]:
    if "r_min_norm" in cfg:
        r_min = float(cfg["r_min_norm"])
    elif "r_min_mm" in cfg:
        r_min = mm_to_norm(float(cfg["r_min_mm"]), ctx.wafer_radius_mm)
    else:
        r_min = float(cfg.get("r_min_ratio", 0.1))
    if "r_max_norm" in cfg:
        r_max = float(cfg["r_max_norm"])
    elif "r_max_mm" in cfg:
        r_max = mm_to_norm(float(cfg["r_max_mm"]), ctx.wafer_radius_mm)
    else:
        r_max = float(cfg.get("r_max_ratio", 1.0))
    if r_min < 0 or r_max > 1.0 or r_min >= r_max:
        raise ValueError("invalid radial range")
    return r_min, r_max


def _resolve_sigma_perp_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "sigma_perp_norm" in cfg:
        sigma = float(cfg["sigma_perp_norm"])
    elif "sigma_perp_mm" in cfg:
        sigma = mm_to_norm(float(cfg["sigma_perp_mm"]), ctx.wafer_radius_mm)
    else:
        sigma = float(cfg.get("sigma_perp_ratio", 0.01))
    if sigma < 0:
        raise ValueError("sigma_perp must be non-negative")
    return sigma


def _resolve_angle_rad(cfg: Mapping[str, Any]) -> float:
    if "angle_rad" in cfg:
        return float(cfg["angle_rad"])
    if "angle_deg" in cfg:
        return radians(float(cfg["angle_deg"]))
    return 0.0


def _resolve_segment_half_length_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "segment_half_length_norm" in cfg:
        return float(cfg["segment_half_length_norm"])
    if "segment_half_length_mm" in cfg:
        return mm_to_norm(float(cfg["segment_half_length_mm"]), ctx.wafer_radius_mm)
    if "segment_half_length_ratio" in cfg:
        return float(cfg["segment_half_length_ratio"])
    if "length_norm" in cfg:
        return float(cfg["length_norm"]) * 0.5
    if "length_mm" in cfg:
        return mm_to_norm(float(cfg["length_mm"]), ctx.wafer_radius_mm) * 0.5
    length_ratio = float(cfg.get("length_ratio", 1.0))
    return length_ratio


def _resolve_offset_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    if "offset_norm" in cfg:
        return float(cfg["offset_norm"])
    if "offset_mm" in cfg:
        return mm_to_norm(float(cfg["offset_mm"]), ctx.wafer_radius_mm)
    return float(cfg.get("offset_ratio", 0.0))


def _ensure_iterable(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return [value]


def _allocate_counts(total: int, n_lines: int) -> list[int]:
    if n_lines <= 0:
        return []
    base = total // n_lines
    counts = [base for _ in range(n_lines)]
    remainder = total - base * n_lines
    for idx in range(remainder):
        counts[idx] += 1
    return counts


def _sample_radial_segment(
    rng: Any,
    count: int,
    *,
    angle: float,
    r_min: float,
    r_max: float,
    sigma_perp: float,
) -> list[tuple[float, float]]:
    dir_x = cos(angle)
    dir_y = sin(angle)
    perp_x = -dir_y
    perp_y = dir_x
    out: list[tuple[float, float]] = []
    max_attempts = count * 40
    attempts = 0
    while len(out) < count and attempts < max_attempts:
        attempts += 1
        t = rng.uniform(r_min, r_max)
        offset = rng.gauss(0.0, sigma_perp) if sigma_perp > 0 else 0.0
        x = dir_x * t + perp_x * offset
        y = dir_y * t + perp_y * offset
        r_norm = hypot(x, y)
        if r_norm > r_max or r_norm > 1.0:
            continue
        theta_rad = atan2(y, x) % tau
        out.append((r_norm, theta_rad))
    while len(out) < count:
        t = rng.uniform(r_min, r_max)
        x = dir_x * t
        y = dir_y * t
        r_norm = min(hypot(x, y), 1.0)
        theta_rad = atan2(y, x) % tau
        out.append((r_norm, theta_rad))
    return out
