from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    SCHEMA_VERSION,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.metrics.size_stats import compute_size_stats
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import input_payload, read_table, resolve_input_paths

_REQUIRED_QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
_SIZE_MODEL_PREFIX = "wafer_particles.size_model."


@register_process("wafer_particles.process.size_qc")
class SizeQcProcess(BaseProcess):
    name = "wafer_particles.process.size_qc"

    def run(self, writer) -> None:
        writer.log("size_qc start")
        size_qc_cfg = _resolve_size_qc_cfg(self.cfg)
        input_cfg = _read_mapping(size_qc_cfg.get("input"), "wafer_particles.size_qc.input")
        paths = resolve_input_paths(input_cfg, repo_root=writer.repo_root)

        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        validate_particles_table(particles)
        validate_samples_table(samples)

        tail_ratio = _resolve_tail_ratio(size_qc_cfg.get("tail_ratio"))
        quantiles = _resolve_quantiles(size_qc_cfg.get("quantiles"), tail_ratio)
        ks_cfg = _resolve_ks_cfg(size_qc_cfg.get("ks"))

        sample_sizes = _collect_sample_sizes(particles)
        sample_meta = _collect_sample_meta(samples, writer.log)
        sample_ids = sorted(set(sample_sizes.keys()) | set(sample_meta.keys()))

        quantile_cols = _quantile_columns(quantiles)
        rows: list[dict[str, Any]] = []
        size_model_buckets: dict[str, dict[str, Any]] = {}

        for sample_id in sample_ids:
            sizes = sample_sizes.get(sample_id, [])
            meta = sample_meta.get(sample_id, {})
            size_model = meta.get("size_model")
            size_params = meta.get("size_params")
            stats = _compute_sample_stats(sizes, quantiles, tail_ratio)
            ks_model, ks_stat = _compute_ks_stat(
                sizes,
                size_model,
                size_params,
                enabled=ks_cfg["enabled"],
                min_count=ks_cfg["min_count"],
            )

            row = {
                "sample_id": sample_id,
                "size_model": size_model or "",
                "n_particles": stats["count"],
                "size_mean": stats["mean"],
                "size_std": stats["std"],
                "size_median": stats["median"],
                "size_skewness": stats["skewness"],
                "size_kurtosis": stats["kurtosis"],
                "size_tail_ratio": stats["tail_ratio"],
                "ks_model": ks_model or "",
                "ks_stat": ks_stat,
            }
            for q in quantile_cols:
                row[_format_quantile_col(q)] = stats["quantiles"].get(_quantile_key(q))
            rows.append(row)

            bucket_key = size_model or "unknown"
            bucket = size_model_buckets.setdefault(bucket_key, {"sample_ids": [], "sizes": []})
            bucket["sample_ids"].append(sample_id)
            if sizes:
                bucket["sizes"].extend(sizes)

        size_model_mix = _build_size_model_mix(size_model_buckets, len(sample_ids), quantiles)
        summary_payload = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": input_payload(paths),
            "quantiles": quantiles,
            "tail_ratio": {"low": tail_ratio["low"], "high": tail_ratio["high"]},
            "summary": {
                "total_samples": len(sample_ids),
                "total_particles": len(particles),
                "size_models": len(size_model_mix),
            },
        }

        writer.write_json("metrics/size_qc_summary.json", summary_payload)
        _write_size_stats_csv(writer.run_dir / "reports" / "size_stats.csv", rows, quantile_cols)
        writer.write_json(
            "reports/size_model_mix.json",
            {
                **summary_payload,
                "size_models": size_model_mix,
            },
        )
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=size_qc\n",
            encoding="utf-8",
        )
        writer.log("size_qc complete")


def _resolve_size_qc_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    size_qc_cfg = wp_cfg.get("size_qc")
    if not isinstance(size_qc_cfg, Mapping):
        raise ValueError("wafer_particles.size_qc config is required")
    return dict(size_qc_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _resolve_tail_ratio(cfg: Any) -> dict[str, float]:
    low = 0.5
    high = 0.95
    if isinstance(cfg, Mapping):
        if cfg.get("low") is not None:
            low = float(cfg["low"])
        elif cfg.get("low_quantile") is not None:
            low = float(cfg["low_quantile"])
        if cfg.get("high") is not None:
            high = float(cfg["high"])
        elif cfg.get("high_quantile") is not None:
            high = float(cfg["high_quantile"])
    if not (0.0 < low < high < 1.0):
        raise ValueError("tail_ratio quantiles must satisfy 0 < low < high < 1")
    return {"low": low, "high": high}


def _resolve_quantiles(value: Any, tail_ratio: Mapping[str, float]) -> list[float]:
    quantiles: list[float] = []
    if value is None:
        quantiles = []
    elif not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise ValueError("quantiles must be a list")
    else:
        quantiles = [float(item) for item in value]
    for q in quantiles:
        if not 0.0 <= q <= 1.0:
            raise ValueError("quantiles must be in [0,1]")
    quantile_set = set(quantiles)
    quantile_set.update(_REQUIRED_QUANTILES)
    quantile_set.add(float(tail_ratio["low"]))
    quantile_set.add(float(tail_ratio["high"]))
    return sorted(quantile_set)


def _resolve_ks_cfg(cfg: Any) -> dict[str, Any]:
    enabled = True
    min_count = 5
    if isinstance(cfg, Mapping):
        if cfg.get("enabled") is not None:
            enabled = bool(cfg["enabled"])
        if cfg.get("min_count") is not None:
            min_count = int(cfg["min_count"])
    if min_count < 2:
        min_count = 2
    return {"enabled": enabled, "min_count": min_count}


def _collect_sample_sizes(particles: list[dict[str, Any]]) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for particle in particles:
        sample_id = particle.get("sample_id")
        if sample_id is None:
            continue
        size = particle.get("size_um")
        if size is None:
            continue
        grouped.setdefault(str(sample_id), []).append(float(size))
    return grouped


def _collect_sample_meta(
    samples: list[dict[str, Any]],
    log_fn,
) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for sample in samples:
        sample_id = sample.get("sample_id")
        if sample_id is None:
            continue
        size_model = sample.get("size_model")
        size_params = _parse_size_params(sample.get("size_params_json"), log_fn)
        meta[str(sample_id)] = {
            "size_model": str(size_model) if size_model is not None else None,
            "size_params": size_params,
        }
    return meta


def _parse_size_params(value: Any, log_fn) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            log_fn("size_params_json parse failed; skipping KS stats for sample")
            return None
        if isinstance(data, Mapping):
            return dict(data)
    return None


def _quantile_key(q: float) -> float:
    return round(float(q), 6)


def _quantile_columns(quantiles: list[float]) -> list[float]:
    return [q for q in quantiles if abs(q - 0.5) > 1e-6]


def _format_quantile_col(q: float) -> str:
    return f"size_q{int(round(q * 100)):02d}"


def _compute_sample_stats(
    values: list[float],
    quantiles: list[float],
    tail_ratio: Mapping[str, float],
) -> dict[str, Any]:
    count = len(values)
    if count == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "median": None,
            "quantiles": {},
            "skewness": None,
            "kurtosis": None,
            "tail_ratio": None,
        }
    sorted_values = sorted(values)
    mean = sum(sorted_values) / count
    variance = sum((value - mean) ** 2 for value in sorted_values) / count
    std = math.sqrt(variance)
    quantile_map = {
        _quantile_key(q): _percentile(sorted_values, q) for q in quantiles
    }
    median = quantile_map.get(_quantile_key(0.5))
    skewness = None
    kurtosis = None
    if count >= 2 and variance > 0:
        m2 = variance
        m3 = sum((value - mean) ** 3 for value in sorted_values) / count
        m4 = sum((value - mean) ** 4 for value in sorted_values) / count
        skewness = m3 / (m2 ** 1.5)
        kurtosis = (m4 / (m2 * m2)) - 3.0
    low_q = quantile_map.get(_quantile_key(tail_ratio["low"]))
    high_q = quantile_map.get(_quantile_key(tail_ratio["high"]))
    ratio = None
    if low_q not in (None, 0.0) and high_q is not None:
        ratio = float(high_q) / float(low_q)
    return {
        "count": count,
        "mean": mean,
        "std": std,
        "median": median,
        "quantiles": quantile_map,
        "skewness": skewness,
        "kurtosis": kurtosis,
        "tail_ratio": ratio,
    }


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return math.nan
    if q <= 0:
        return float(sorted_values[0])
    if q >= 1:
        return float(sorted_values[-1])
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return float(sorted_values[lower])
    fraction = pos - lower
    lower_value = float(sorted_values[lower])
    upper_value = float(sorted_values[upper])
    return lower_value * (1.0 - fraction) + upper_value * fraction


def _compute_ks_stat(
    values: list[float],
    size_model: str | None,
    size_params: Mapping[str, Any] | None,
    *,
    enabled: bool,
    min_count: int,
) -> tuple[str | None, float | None]:
    if not enabled or not size_model or not size_params or len(values) < min_count:
        return None, None
    model_name = _normalize_size_model_name(size_model)
    cdf_fn = _build_cdf(model_name, size_params)
    if cdf_fn is None:
        return None, None
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n == 0:
        return None, None
    max_diff = 0.0
    for idx, value in enumerate(sorted_values, start=1):
        cdf_val = cdf_fn(float(value))
        if cdf_val is None:
            return None, None
        cdf_val = min(max(float(cdf_val), 0.0), 1.0)
        emp = idx / n
        prev = (idx - 1) / n
        diff = max(abs(cdf_val - emp), abs(cdf_val - prev))
        if diff > max_diff:
            max_diff = diff
    return model_name, max_diff


def _build_cdf(model_name: str, params: Mapping[str, Any]) -> Any | None:
    name = _normalize_size_model_name(model_name).lower()
    min_um = _optional_float(params.get("min_um"))
    max_um = _optional_float(params.get("max_um"))
    base = None
    if name == "gaussian":
        mean_um = _optional_float(params.get("mean_um"))
        std_um = _optional_float(params.get("std_um"))
        if mean_um is None or std_um is None or std_um <= 0:
            return None
        base = lambda x: _gaussian_cdf(x, mean_um, std_um)
    elif name == "lognormal":
        mu_log = _optional_float(params.get("mu_log"))
        sigma_log = _optional_float(params.get("sigma_log"))
        if mu_log is None or sigma_log is None or sigma_log <= 0:
            return None
        base = lambda x: _lognormal_cdf(x, mu_log, sigma_log)
    elif name == "weibull":
        k = _optional_float(params.get("k"))
        lambda_um = _optional_float(params.get("lambda_um"))
        if k is None or lambda_um is None or k <= 0 or lambda_um <= 0:
            return None
        base = lambda x: _weibull_cdf(x, k, lambda_um)
    elif name == "pareto":
        alpha = _optional_float(params.get("alpha"))
        xm_um = _optional_float(params.get("xm_um"))
        if alpha is None or xm_um is None or alpha <= 0 or xm_um <= 0:
            return None
        base = lambda x: _pareto_cdf(x, alpha, xm_um)
    elif name == "mixture":
        components = params.get("components")
        if not isinstance(components, list) or not components:
            return None
        base = _mixture_cdf_builder(components)
        if base is None:
            return None
    if base is None:
        return None
    return _wrap_bounds(base, min_um, max_um)


def _mixture_cdf_builder(components: list[Any]) -> Any | None:
    resolved: list[tuple[float, Any]] = []
    total_weight = 0.0
    for component in components:
        if not isinstance(component, Mapping):
            return None
        weight = component.get("weight")
        if weight is None:
            return None
        weight_value = float(weight)
        if weight_value <= 0:
            return None
        model_type = component.get("model_type") or component.get("type") or component.get("model")
        params = component.get("params")
        if model_type is None or not isinstance(params, Mapping):
            return None
        cdf_fn = _build_cdf(str(model_type), params)
        if cdf_fn is None:
            return None
        resolved.append((weight_value, cdf_fn))
        total_weight += weight_value
    if total_weight <= 0:
        return None

    def _cdf(x: float) -> float:
        acc = 0.0
        for weight, cdf_fn in resolved:
            acc += (weight / total_weight) * float(cdf_fn(x))
        return acc

    return _cdf


def _wrap_bounds(cdf_fn, min_um: float | None, max_um: float | None):
    def _wrapped(x: float) -> float | None:
        if min_um is not None and x < min_um:
            return 0.0
        if max_um is not None and x >= max_um:
            return 1.0
        return cdf_fn(x)

    return _wrapped


def _gaussian_cdf(x: float, mean: float, std: float) -> float:
    z = (x - mean) / (std * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


def _lognormal_cdf(x: float, mu_log: float, sigma_log: float) -> float:
    if x <= 0:
        return 0.0
    z = (math.log(x) - mu_log) / (sigma_log * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


def _weibull_cdf(x: float, k: float, lambda_um: float) -> float:
    if x < 0:
        return 0.0
    return 1.0 - math.exp(-((x / lambda_um) ** k))


def _pareto_cdf(x: float, alpha: float, xm_um: float) -> float:
    min_x = 2.0 * xm_um
    if x < min_x:
        return 0.0
    y = (x / xm_um) - 1.0
    if y <= 0:
        return 0.0
    return 1.0 - (y ** (-alpha))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_size_model_name(name: str) -> str:
    return name[len(_SIZE_MODEL_PREFIX) :] if name.startswith(_SIZE_MODEL_PREFIX) else name


def _build_size_model_mix(
    buckets: Mapping[str, Mapping[str, Any]],
    total_samples: int,
    quantiles: list[float],
) -> dict[str, Any]:
    mix: dict[str, Any] = {}
    for model, bucket in buckets.items():
        sizes = bucket.get("sizes", [])
        size_stats = compute_size_stats(sizes, quantiles=quantiles)
        n_samples = len(bucket.get("sample_ids", []))
        mix[model] = {
            "n_samples": n_samples,
            "sample_ratio": (n_samples / total_samples) if total_samples else None,
            "n_particles": len(sizes),
            "size_stats": size_stats,
        }
    return mix


def _write_size_stats_csv(path: Path, rows: list[dict[str, Any]], quantiles: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sample_id",
        "size_model",
        "n_particles",
        "size_mean",
        "size_std",
        "size_median",
        "size_skewness",
        "size_kurtosis",
        "size_tail_ratio",
        "ks_model",
        "ks_stat",
    ]
    fieldnames.extend(_format_quantile_col(q) for q in quantiles)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_format_row(row, fieldnames))


def _format_row(row: Mapping[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    formatted: dict[str, Any] = {}
    for key in fieldnames:
        value = row.get(key)
        formatted[key] = "" if value is None else value
    return formatted


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME
