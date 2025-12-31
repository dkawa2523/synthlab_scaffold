from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from synthlab.domains.wafer_particles import validate_particles_table, validate_samples_table
from synthlab.domains.wafer_particles.metrics.size_stats import compute_size_stats
from synthlab.framework.registry import register_model
from synthlab.processes._wafer_particles_io import read_table

MODEL_NAME = "wafer_particles.model.baseline_centroid"
DEFAULT_R_BINS = {"start": 0.0, "stop": 150.0, "count": 30}
DEFAULT_THETA_BINS = {"start": 0.0, "stop": 6.283185307179586, "count": 36}
DEFAULT_SIZE_QUANTILES = (0.25, 0.5, 0.75)


@register_model(MODEL_NAME)
def baseline_centroid_model(
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

    params = _read_params(cfg)
    input_payload = _read_mapping(inputs.get("input"), "inputs.input")

    particles_path = Path(str(input_payload.get("particles_path")))
    samples_path = Path(str(input_payload.get("samples_path")))
    if not particles_path.exists():
        raise ValueError(f"particles_path not found: {particles_path}")
    if not samples_path.exists():
        raise ValueError(f"samples_path not found: {samples_path}")

    particles = read_table(particles_path)
    samples = read_table(samples_path)
    validate_particles_table(particles)
    validate_samples_table(samples)

    split_map = _load_split_map(input_payload)
    model_info = _read_mapping(inputs.get("model"), "inputs.model", required=False)
    feature_spec = _resolve_feature_spec(params, model_info)
    split_name = _resolve_split_name(stage, params, model_info, split_map)

    sample_ids = _select_sample_ids(samples, split_map, split_name)
    if sample_ids is None and split_map and split_name:
        split_name = None
    features, labels, ordered_ids, ordered_splits = _build_feature_matrix(
        samples,
        particles,
        sample_ids=sample_ids,
        split_map=split_map,
        feature_spec=feature_spec,
    )

    if stage == "train":
        standardize = bool(params.get("standardize", True))
        scaled, scaler = _standardize_features(features, standardize=standardize)
        label_order = sorted(set(labels))
        centroids, counts = _compute_centroids(scaled, labels, label_order)
        preds, metrics = _evaluate_predictions(
            stage,
            scaled,
            labels,
            ordered_ids,
            ordered_splits,
            label_order,
            centroids,
            split_name,
            include_distances=bool(params.get("include_distances", False)),
        )
        model_payload = {
            "name": MODEL_NAME,
            "stage": "train",
            "seed": seed,
            "feature_spec": feature_spec,
            "feature_names": _feature_names(feature_spec),
            "labels": label_order,
            "centroids": centroids.tolist(),
            "scaler": scaler,
            "train_split": split_name,
            "eval_split": str(params.get("eval_split") or ""),
            "train_counts": counts,
        }
        return {
            "model_info": model_payload,
            "metrics": metrics,
            "preds": preds,
        }

    trained = _require_trained_model(model_info)
    label_order = _load_label_order(trained)
    centroids = _load_centroids(trained, label_order)
    scaler = trained.get("scaler") or {}
    scaled = _apply_scaler(features, scaler)
    preds, metrics = _evaluate_predictions(
        stage,
        scaled,
        labels,
        ordered_ids,
        ordered_splits,
        label_order,
        centroids,
        split_name,
        include_distances=bool(params.get("include_distances", False)),
    )
    metrics["model_name"] = trained.get("model_name") or trained.get("name") or MODEL_NAME
    return {
        "metrics": metrics,
        "preds": preds,
    }


def _read_params(cfg: Mapping[str, Any]) -> dict[str, Any]:
    params = cfg.get("params")
    if params is None:
        return dict(cfg)
    if not isinstance(params, Mapping):
        raise ValueError("model.params must be a mapping")
    return dict(params)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _resolve_feature_spec(params: Mapping[str, Any], model_info: Mapping[str, Any]) -> dict[str, Any]:
    trained_spec = model_info.get("feature_spec") if isinstance(model_info, Mapping) else None
    if isinstance(trained_spec, Mapping):
        return dict(trained_spec)

    features_cfg = _read_mapping(params.get("features"), "params.features", required=False)
    r_cfg = features_cfg.get("r")
    theta_cfg = features_cfg.get("theta")
    size_cfg = _read_mapping(features_cfg.get("size"), "params.features.size", required=False)

    r_edges = _resolve_edges(r_cfg, "features.r", DEFAULT_R_BINS)
    theta_edges = _resolve_edges(theta_cfg, "features.theta", DEFAULT_THETA_BINS)
    size_quantiles = _resolve_quantiles(size_cfg.get("quantiles"), DEFAULT_SIZE_QUANTILES)
    include_mean = bool(size_cfg.get("include_mean", True))
    include_std = bool(size_cfg.get("include_std", True))
    normalize_hist = bool(features_cfg.get("normalize_hist", params.get("normalize_hist", True)))

    return {
        "r_edges": r_edges,
        "theta_edges": theta_edges,
        "size_quantiles": list(size_quantiles),
        "include_size_mean": include_mean,
        "include_size_std": include_std,
        "normalize_hist": normalize_hist,
        "r_key": str(features_cfg.get("r_key", "r_mm")),
        "theta_key": str(features_cfg.get("theta_key", "theta_rad")),
        "size_key": str(features_cfg.get("size_key", "size_um")),
        "n_particles_key": str(features_cfg.get("n_particles_key", "n_particles")),
    }


def _resolve_edges(cfg: Any, name: str, defaults: Mapping[str, Any]) -> list[float]:
    if cfg is None:
        cfg = defaults
    if isinstance(cfg, Mapping) and "edges" in cfg:
        edges = [float(value) for value in cfg["edges"]]
    elif isinstance(cfg, Mapping):
        start = cfg.get("start")
        stop = cfg.get("stop")
        count = cfg.get("count")
        if start is None or stop is None or count is None:
            raise ValueError(f"{name} must define edges or start/stop/count")
        edges = _linspace(float(start), float(stop), int(count))
    else:
        raise ValueError(f"{name} must be a mapping")
    if len(edges) < 2:
        raise ValueError(f"{name} must have at least 2 edges")
    if any(edges[i] >= edges[i + 1] for i in range(len(edges) - 1)):
        raise ValueError(f"{name} edges must be strictly increasing")
    return edges


def _linspace(start: float, stop: float, count: int) -> list[float]:
    if count <= 0:
        raise ValueError("count must be positive")
    step = (stop - start) / count
    return [start + step * idx for idx in range(count + 1)]


def _resolve_quantiles(value: Any, defaults: Sequence[float]) -> list[float]:
    if value is None:
        return [float(q) for q in defaults]
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        raise ValueError("size quantiles must be a list")
    return [float(q) for q in value]


def _load_split_map(input_payload: Mapping[str, Any]) -> dict[str, str]:
    splits_path = input_payload.get("splits_path")
    if splits_path:
        path = Path(str(splits_path))
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, Mapping):
                sample_ids = data.get("sample_ids")
                if isinstance(sample_ids, Mapping):
                    split_map: dict[str, str] = {}
                    for split_name, ids in sample_ids.items():
                        if not isinstance(ids, Iterable) or isinstance(ids, (str, bytes)):
                            continue
                        for sample_id in ids:
                            split_map[str(sample_id)] = str(split_name)
                    return split_map
    index_samples_path = input_payload.get("index_samples_path")
    if index_samples_path:
        path = Path(str(index_samples_path))
        if path.exists():
            rows = read_table(path)
            split_map = {}
            for row in rows:
                sample_id = row.get("sample_id")
                split = row.get("split")
                if sample_id and split:
                    split_map[str(sample_id)] = str(split)
            return split_map
    return {}


def _resolve_split_name(
    stage: str,
    params: Mapping[str, Any],
    model_info: Mapping[str, Any],
    split_map: Mapping[str, str],
) -> str | None:
    split_cfg = _read_mapping(params.get("splits"), "params.splits", required=False)
    if stage == "train":
        return str(params.get("train_split") or split_cfg.get("train") or "train")
    if stage == "eval":
        return str(
            params.get("eval_split")
            or split_cfg.get("eval")
            or model_info.get("eval_split")
            or "test"
        )
    if stage == "predict":
        return str(params.get("predict_split") or split_cfg.get("predict") or "") or None
    if split_map:
        return sorted(set(split_map.values()))[0]
    return None


def _select_sample_ids(
    samples: Sequence[Mapping[str, Any]],
    split_map: Mapping[str, str],
    split_name: str | None,
) -> set[str] | None:
    if not split_map or not split_name:
        return None
    selected = {sample_id for sample_id, split in split_map.items() if split == split_name}
    if selected:
        return selected
    return None


def _build_feature_matrix(
    samples: Sequence[Mapping[str, Any]],
    particles: Sequence[Mapping[str, Any]],
    *,
    sample_ids: set[str] | None,
    split_map: Mapping[str, str],
    feature_spec: Mapping[str, Any],
) -> tuple[np.ndarray, list[str], list[str], list[str | None]]:
    particles_by_sample: dict[str, list[Mapping[str, Any]]] = {}
    for particle in particles:
        sample_id = particle.get("sample_id")
        if sample_id is None:
            continue
        key = str(sample_id)
        particles_by_sample.setdefault(key, []).append(particle)

    ordered_ids: list[str] = []
    labels: list[str] = []
    splits: list[str | None] = []
    feature_rows: list[np.ndarray] = []
    for row in samples:
        sample_id = row.get("sample_id")
        if sample_id is None:
            continue
        sample_id = str(sample_id)
        if sample_ids is not None and sample_id not in sample_ids:
            continue
        label = row.get("label")
        labels.append(str(label) if label is not None else "")
        ordered_ids.append(sample_id)
        splits.append(split_map.get(sample_id))
        n_particles = row.get(feature_spec.get("n_particles_key", "n_particles"))
        particles_rows = particles_by_sample.get(sample_id, [])
        feature_rows.append(
            _extract_features(
                particles_rows,
                int(n_particles) if n_particles is not None else len(particles_rows),
                feature_spec,
            )
        )

    if not feature_rows:
        raise ValueError("no samples available for feature extraction")
    features = np.vstack(feature_rows)
    return features, labels, ordered_ids, splits


def _extract_features(
    particles: Sequence[Mapping[str, Any]],
    n_particles: int,
    feature_spec: Mapping[str, Any],
) -> np.ndarray:
    r_key = str(feature_spec.get("r_key", "r_mm"))
    theta_key = str(feature_spec.get("theta_key", "theta_rad"))
    size_key = str(feature_spec.get("size_key", "size_um"))
    r_edges = [float(value) for value in feature_spec["r_edges"]]
    theta_edges = [float(value) for value in feature_spec["theta_edges"]]
    normalize_hist = bool(feature_spec.get("normalize_hist", True))

    r_values = np.array(
        [float(p[r_key]) for p in particles if p.get(r_key) is not None],
        dtype=float,
    )
    theta_values = np.array(
        [float(p[theta_key]) for p in particles if p.get(theta_key) is not None],
        dtype=float,
    )
    size_values = [float(p[size_key]) for p in particles if p.get(size_key) is not None]

    if theta_values.size:
        theta_values = np.mod(theta_values, theta_edges[-1])

    r_hist, _ = np.histogram(r_values, bins=r_edges)
    theta_hist, _ = np.histogram(theta_values, bins=theta_edges)

    r_hist = r_hist.astype(float)
    theta_hist = theta_hist.astype(float)
    if normalize_hist:
        r_hist = _normalize_hist(r_hist)
        theta_hist = _normalize_hist(theta_hist)

    size_stats = compute_size_stats(size_values, quantiles=feature_spec.get("size_quantiles"))
    size_features: list[float] = []
    if feature_spec.get("include_size_mean", True):
        size_features.append(float(size_stats.get("mean") or 0.0))
    if feature_spec.get("include_size_std", True):
        size_features.append(float(size_stats.get("std") or 0.0))
    for q in feature_spec.get("size_quantiles", []):
        key = _format_quantile_key(float(q))
        size_features.append(float(size_stats.get("quantiles", {}).get(key) or 0.0))

    return np.concatenate([[float(n_particles)], r_hist, theta_hist, np.array(size_features, dtype=float)])


def _normalize_hist(values: np.ndarray) -> np.ndarray:
    total = float(values.sum())
    if total <= 0.0:
        return np.zeros_like(values, dtype=float)
    return values / total


def _standardize_features(
    features: np.ndarray,
    *,
    standardize: bool,
) -> tuple[np.ndarray, dict[str, list[float]]]:
    if not standardize:
        return (
            features,
            {
                "mean": [0.0 for _ in range(features.shape[1])],
                "std": [1.0 for _ in range(features.shape[1])],
            },
        )
    mean = features.mean(axis=0)
    std = features.std(axis=0)
    std = np.where(std > 0.0, std, 1.0)
    scaled = (features - mean) / std
    return scaled, {"mean": mean.tolist(), "std": std.tolist()}


def _apply_scaler(features: np.ndarray, scaler: Mapping[str, Any]) -> np.ndarray:
    mean = scaler.get("mean")
    std = scaler.get("std")
    if mean is None or std is None:
        return features
    mean_arr = np.array(mean, dtype=float)
    std_arr = np.array(std, dtype=float)
    std_arr = np.where(std_arr > 0.0, std_arr, 1.0)
    return (features - mean_arr) / std_arr


def _compute_centroids(
    features: np.ndarray,
    labels: Sequence[str],
    label_order: Sequence[str],
) -> tuple[np.ndarray, dict[str, int]]:
    centroids: list[np.ndarray] = []
    counts: dict[str, int] = {}
    for label in label_order:
        mask = np.array([lbl == label for lbl in labels], dtype=bool)
        count = int(mask.sum())
        counts[label] = count
        if count == 0:
            centroids.append(np.zeros((features.shape[1],), dtype=float))
        else:
            centroids.append(features[mask].mean(axis=0))
    return np.vstack(centroids), counts


def _evaluate_predictions(
    stage: str,
    features: np.ndarray,
    labels: Sequence[str],
    sample_ids: Sequence[str],
    splits: Sequence[str | None],
    label_order: Sequence[str],
    centroids: np.ndarray,
    split_name: str | None,
    *,
    include_distances: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    preds, distances = _predict(features, label_order, centroids)
    rows: list[dict[str, Any]] = []
    for idx, sample_id in enumerate(sample_ids):
        payload = {
            "sample_id": sample_id,
            "true_label": labels[idx] if labels[idx] else None,
            "pred_label": preds[idx],
            "split": splits[idx],
            "distance": float(distances[idx]),
        }
        rows.append(payload)

    accuracy, per_label, confusion, unknown = _classification_metrics(labels, preds, label_order)
    metrics = {
        "stage": stage,
        "split": split_name,
        "n_samples": len(sample_ids),
        "labels": list(label_order),
        "accuracy": accuracy,
        "per_label_accuracy": per_label,
        "confusion_matrix": confusion,
        "unknown_true_labels": unknown,
    }
    if include_distances:
        metrics["distance_mean"] = float(np.mean(distances)) if distances.size else None
    return rows, metrics


def _predict(
    features: np.ndarray,
    label_order: Sequence[str],
    centroids: np.ndarray,
) -> tuple[list[str], np.ndarray]:
    if centroids.size == 0:
        raise ValueError("centroids are empty")
    diffs = features[:, None, :] - centroids[None, :, :]
    dist = np.sum(diffs**2, axis=2)
    best = np.argmin(dist, axis=1)
    preds = [label_order[int(idx)] for idx in best]
    best_dist = dist[np.arange(dist.shape[0]), best]
    return preds, best_dist


def _classification_metrics(
    true_labels: Sequence[str],
    pred_labels: Sequence[str],
    label_order: Sequence[str],
) -> tuple[float | None, dict[str, float], list[list[int]], int]:
    index = {label: idx for idx, label in enumerate(label_order)}
    matrix = [[0 for _ in label_order] for _ in label_order]
    total = 0
    correct = 0
    unknown = 0
    per_label_counts: dict[str, list[int]] = {label: [0, 0] for label in label_order}

    for true_label, pred_label in zip(true_labels, pred_labels):
        if true_label not in index:
            unknown += 1
            continue
        true_idx = index[true_label]
        pred_idx = index[pred_label]
        matrix[true_idx][pred_idx] += 1
        total += 1
        if true_idx == pred_idx:
            correct += 1
            per_label_counts[true_label][0] += 1
        per_label_counts[true_label][1] += 1

    accuracy = (correct / total) if total else None
    per_label = {
        label: (counts[0] / counts[1]) if counts[1] else None
        for label, counts in per_label_counts.items()
    }
    return accuracy, per_label, matrix, unknown


def _feature_names(feature_spec: Mapping[str, Any]) -> list[str]:
    names = ["n_particles"]
    r_bins = len(feature_spec.get("r_edges", [])) - 1
    theta_bins = len(feature_spec.get("theta_edges", [])) - 1
    names.extend([f"hist_r_bin_{idx}" for idx in range(r_bins)])
    names.extend([f"hist_theta_bin_{idx}" for idx in range(theta_bins)])
    if feature_spec.get("include_size_mean", True):
        names.append("size_mean")
    if feature_spec.get("include_size_std", True):
        names.append("size_std")
    for q in feature_spec.get("size_quantiles", []):
        names.append(f"size_{_format_quantile_key(float(q))}")
    return names


def _format_quantile_key(q: float) -> str:
    if 0.0 <= q <= 1.0:
        return f"p{int(round(q * 100)):02d}"
    return str(q)


def _require_trained_model(model_info: Mapping[str, Any]) -> Mapping[str, Any]:
    if not model_info:
        raise ValueError("model info is required for eval/predict")
    return model_info


def _load_label_order(model_info: Mapping[str, Any]) -> list[str]:
    labels = model_info.get("labels")
    if not isinstance(labels, Sequence) or isinstance(labels, (str, bytes)):
        raise ValueError("model_info.labels must be a list")
    return [str(label) for label in labels]


def _load_centroids(model_info: Mapping[str, Any], label_order: Sequence[str]) -> np.ndarray:
    centroids = model_info.get("centroids")
    if centroids is None:
        raise ValueError("model_info.centroids is required")
    centroids_array = np.array(centroids, dtype=float)
    if centroids_array.shape[0] != len(label_order):
        raise ValueError("centroids and labels length mismatch")
    return centroids_array
