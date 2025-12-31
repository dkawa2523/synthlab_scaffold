from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_param_estimator

from .common import angular_distance_rad, mean, quantile, std


@register_param_estimator("wafer_particles.param_estimator.radial_lines")
def estimate(cfg: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    stats = payload.get("stats")
    if not isinstance(stats, Mapping):
        return {}
    hist = stats.get("theta_hist")
    centers = stats.get("theta_bin_centers")
    if not isinstance(hist, list) or not isinstance(centers, list) or not hist:
        return {}
    hist_mean = mean(hist) or 0.0
    hist_std = std(hist, mean_value=hist_mean) or 0.0
    peak_std_factor = 1.0
    min_peak_count = 2.0
    jitter_quantile = 0.9
    if isinstance(cfg, Mapping):
        if cfg.get("peak_std_factor") is not None:
            peak_std_factor = float(cfg.get("peak_std_factor"))
        if cfg.get("min_peak_count") is not None:
            min_peak_count = float(cfg.get("min_peak_count"))
        if cfg.get("jitter_quantile") is not None:
            jitter_quantile = float(cfg.get("jitter_quantile"))
    threshold = max(min_peak_count, hist_mean + hist_std * peak_std_factor)
    n_bins = len(hist)
    peaks: list[int] = []
    for idx in range(n_bins):
        prev_val = hist[idx - 1]
        next_val = hist[(idx + 1) % n_bins]
        if hist[idx] >= threshold and hist[idx] > prev_val and hist[idx] > next_val:
            peaks.append(idx)
    angles = [float(centers[idx]) for idx in peaks]
    n_lines = len(angles)
    jitter_rad = None
    theta_values = payload.get("theta_values")
    if angles and isinstance(theta_values, list) and theta_values:
        distances = [
            min(angular_distance_rad(float(theta), angle) for angle in angles) for theta in theta_values
        ]
        jitter_rad = quantile(distances, jitter_quantile)
    return {
        "n_lines": n_lines,
        "angles_rad": angles,
        "angular_jitter_rad": jitter_rad,
    }
