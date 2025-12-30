from __future__ import annotations

from math import cos, pi, sqrt, tau
from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .common import build_particle, resolve_sample_ctx, sample_poisson


@register_pattern("wafer_particles.pattern.inhomogeneous_poisson")
def generate(
    cfg: Mapping[str, Any],
    rng: Any,
    sample_ctx: Mapping[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    ctx = resolve_sample_ctx(cfg, sample_ctx)
    mean_particles = _resolve_mean_particles(cfg, ctx)
    if mean_particles <= 0:
        return []

    radial_power = float(cfg.get("radial_power", 0.0))
    angular_amplitude = float(cfg.get("angular_amplitude", 0.0))
    if angular_amplitude < 0.0 or angular_amplitude >= 1.0:
        raise ValueError("angular_amplitude must be in [0, 1)")
    angular_harmonic = int(cfg.get("angular_harmonic", 1))
    if angular_harmonic <= 0:
        raise ValueError("angular_harmonic must be positive")
    phase_rad = _resolve_phase_rad(cfg)

    radial_mean = _radial_mean(radial_power)
    if radial_mean <= 0.0:
        raise ValueError("radial_power produces non-positive mean intensity")
    area = pi * ctx.wafer_radius_mm * ctx.wafer_radius_mm
    base_rate = float(mean_particles) / (area * radial_mean)
    max_intensity = base_rate * (1.0 + angular_amplitude)

    n_points = sample_poisson(rng, float(mean_particles))
    if n_points <= 0:
        return []

    particles: list[dict[str, float | str]] = []
    max_attempts = int(cfg.get("max_attempts", max(100, n_points * 50)))
    attempts = 0
    while len(particles) < n_points and attempts < max_attempts:
        attempts += 1
        r_mm = ctx.wafer_radius_mm * sqrt(rng.random())
        theta_rad = rng.random() * tau
        r_ratio = r_mm / ctx.wafer_radius_mm if ctx.wafer_radius_mm > 0 else 0.0
        radial_factor = _radial_factor(r_ratio, radial_power)
        angular_factor = 1.0 + angular_amplitude * cos(angular_harmonic * (theta_rad - phase_rad))
        intensity = base_rate * radial_factor * angular_factor
        if rng.random() * max_intensity <= intensity:
            particles.append(build_particle(r_mm, theta_rad))

    while len(particles) < n_points:
        r_mm = ctx.wafer_radius_mm * sqrt(rng.random())
        theta_rad = rng.random() * tau
        particles.append(build_particle(r_mm, theta_rad))

    return particles


def _resolve_mean_particles(cfg: Mapping[str, Any], ctx: Any) -> float:
    mean_particles = cfg.get("mean_particles")
    if mean_particles is None:
        mean_particles = cfg.get("n_particles")
    if mean_particles is None:
        mean_particles = ctx.n_particles
    mean_particles = float(mean_particles)
    if mean_particles < 0:
        raise ValueError("mean_particles must be non-negative")
    return mean_particles


def _resolve_phase_rad(cfg: Mapping[str, Any]) -> float:
    if "angular_phase_rad" in cfg:
        return float(cfg["angular_phase_rad"])
    if "angular_phase_deg" in cfg:
        return float(cfg["angular_phase_deg"]) * tau / 360.0
    return 0.0


def _radial_factor(r_ratio: float, radial_power: float) -> float:
    r_ratio = min(max(r_ratio, 0.0), 1.0)
    if radial_power >= 0.0:
        return r_ratio ** radial_power
    return (1.0 - r_ratio) ** (-radial_power)


def _radial_mean(radial_power: float) -> float:
    if radial_power >= 0.0:
        return 2.0 / (radial_power + 2.0)
    power = -radial_power
    return 2.0 / ((power + 1.0) * (power + 2.0))
