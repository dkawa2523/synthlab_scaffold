from __future__ import annotations

from math import cos, radians, sin, tau
from typing import Any, Iterable, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .common import build_particle, mm_to_norm
from .geometry import sample_line_segment


@register_pattern("wafer_particles.pattern.radial_lines")
class RadialLines(PatternBase):
    pattern_id = "wafer_particles.pattern.radial_lines"
    touch_edge = True
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
        width_norm = _resolve_width_norm(params, ctx)

        n_lines = len(angles_rad)
        counts = _allocate_counts(ctx.n_particles, n_lines)
        particles: list[dict[str, Any]] = []
        for angle, count in zip(angles_rad, counts):
            if count <= 0:
                continue
            angle = angle + (rng.random() - 0.5) * 2.0 * angular_jitter_rad
            center_r = (r_min_norm + r_max_norm) * 0.5
            center_x = cos(angle) * center_r
            center_y = sin(angle) * center_r
            length_norm = max(0.0, r_max_norm - r_min_norm)
            points = sample_line_segment(
                rng,
                count,
                center_x=center_x,
                center_y=center_y,
                angle_rad=angle,
                length_norm=length_norm,
                width_norm=width_norm,
            )
            for r_norm, theta_rad in points:
                if r_norm < r_min_norm or r_norm > r_max_norm:
                    r_norm = min(max(r_norm, r_min_norm), r_max_norm)
                particles.append(build_particle(r_norm, theta_rad))
        return particles


def _resolve_angles_rad(cfg: Mapping[str, Any]) -> list[float]:
    if "angles_rad" in cfg:
        return [float(value) for value in _ensure_iterable(cfg["angles_rad"])]
    if "angles_deg" in cfg:
        return [radians(float(value)) for value in _ensure_iterable(cfg["angles_deg"])]
    n_lines = int(cfg.get("n_lines", 6))
    if n_lines <= 0:
        raise ValueError("n_lines must be positive")
    offset = float(cfg.get("angle_offset_rad", 0.0))
    return [offset + tau * idx / n_lines for idx in range(n_lines)]


def _resolve_jitter_rad(cfg: Mapping[str, Any]) -> float:
    if "angular_jitter_rad" in cfg:
        return float(cfg["angular_jitter_rad"])
    if "angular_jitter_deg" in cfg:
        return radians(float(cfg["angular_jitter_deg"]))
    return radians(2.0)


def _resolve_width_norm(cfg: Mapping[str, Any], ctx: PatternContext) -> float:
    for key in ("width_norm", "line_width_norm"):
        if key in cfg:
            return max(0.0, float(cfg[key]))
    for key in ("width_mm", "line_width_mm"):
        if key in cfg:
            return max(0.0, mm_to_norm(float(cfg[key]), ctx.wafer_radius_mm))
    ratio = cfg.get("width_ratio", cfg.get("line_width_ratio"))
    if ratio is None:
        return 0.0
    return max(0.0, float(ratio))


def _resolve_radius_range(cfg: Mapping[str, Any], ctx: PatternContext) -> tuple[float, float]:
    if "r_min_norm" in cfg:
        r_min = float(cfg["r_min_norm"])
    elif "r_min_mm" in cfg:
        r_min = mm_to_norm(float(cfg["r_min_mm"]), ctx.wafer_radius_mm)
    else:
        r_min = float(cfg.get("r_min_ratio", 0.0))
    if "r_max_norm" in cfg:
        r_max = float(cfg["r_max_norm"])
    elif "r_max_mm" in cfg:
        r_max = mm_to_norm(float(cfg["r_max_mm"]), ctx.wafer_radius_mm)
    else:
        r_max = float(cfg.get("r_max_ratio", 1.0))
    r_min = max(0.0, min(r_min, 1.0))
    r_max = max(0.0, min(r_max, 1.0))
    if r_min >= r_max:
        raise ValueError("invalid radius range")
    return r_min, r_max


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
