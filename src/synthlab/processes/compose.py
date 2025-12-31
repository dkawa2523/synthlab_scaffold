from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from synthlab.domains.wafer_particles import (
    DOMAIN_NAME,
    PARTICLES_SCHEMA,
    SCHEMA_VERSION,
    SAMPLES_SCHEMA,
    build_manifest,
    validate_particles_table,
    validate_samples_table,
)
from synthlab.domains.wafer_particles.labeling import serialize_label_lists
from synthlab.framework.process import BaseProcess
from synthlab.framework.registry import register_process
from synthlab.processes._wafer_particles_io import input_payload, read_table, resolve_input_paths


@register_process("wafer_particles.process.compose")
class ComposeProcess(BaseProcess):
    name = "wafer_particles.process.compose"

    def run(self, writer) -> None:
        writer.log("compose start")
        wp_cfg = _resolve_wafer_particles_cfg(self.cfg)
        compose_cfg = _read_mapping(wp_cfg.get("compose"), "wafer_particles.compose")
        input_cfg = _read_mapping(
            compose_cfg.get("input"),
            "wafer_particles.compose.input",
            required=False,
        )
        input_run_dir = compose_cfg.get("input_run_dir")
        if input_run_dir and not input_cfg.get("run_dir"):
            input_cfg["run_dir"] = input_run_dir
        if not input_cfg:
            raise ValueError("wafer_particles.compose.input is required")

        paths = resolve_input_paths(
            input_cfg,
            repo_root=writer.repo_root,
            default_process_name="wafer_particles.process.generate",
        )
        particles = read_table(paths.particles_path)
        samples = read_table(paths.samples_path)
        validate_particles_table(particles)
        validate_samples_table(samples)

        sample_id_prefix = str(compose_cfg.get("sample_id_prefix", "compose"))
        seed = _coerce_int(self.cfg.get("seed"), "seed")
        n_samples_out = _coerce_positive_int(compose_cfg.get("n_samples_out"), "wafer_particles.compose.n_samples_out")

        samples_by_id = _index_samples(samples)
        particles_by_sample = _group_particles(particles, samples_by_id.keys())
        label_by_sample = _sample_labels(samples_by_id)
        label_pool = _build_label_pool(label_by_sample)

        component_cfg = _read_mapping(
            compose_cfg.get("component_sampling"),
            "wafer_particles.compose.component_sampling",
            required=False,
        )
        allow_duplicates = bool(component_cfg.get("allow_duplicates", True))
        weight_labels, weight_values = _resolve_component_weights(component_cfg.get("weights"), label_pool)

        n_components_spec = _normalize_n_components_spec(compose_cfg.get("n_components"))
        particle_budget_cfg = _read_mapping(
            compose_cfg.get("particle_budget"),
            "wafer_particles.compose.particle_budget",
            required=False,
        )
        particle_budget_mode = _resolve_particle_budget_mode(particle_budget_cfg)

        particles_out: list[dict[str, Any]] = []
        samples_out: list[dict[str, Any]] = []
        compose_samples_manifest: list[dict[str, Any]] = []
        component_label_distribution: dict[str, int] = {}

        for sample_idx in range(n_samples_out):
            n_components = _sample_n_components(
                n_components_spec,
                random.Random(_derive_seed(seed, sample_idx, "compose_n_components")),
            )
            if not allow_duplicates and n_components > len(weight_labels):
                raise ValueError(
                    "compose.n_components exceeds available labels with allow_duplicates=false"
                )
            labels = _sample_component_labels(
                random.Random(_derive_seed(seed, sample_idx, "compose_labels")),
                weight_labels,
                weight_values,
                n_components,
                allow_duplicates=allow_duplicates,
            )

            component_entries: list[dict[str, Any]] = []
            component_particles: list[list[dict[str, Any]]] = []
            base_counts: list[int] = []
            for component_id, label in enumerate(labels):
                rng_component = random.Random(_derive_seed(seed, sample_idx, f"compose_component_{component_id}"))
                source_sample_id = _choose_source_sample(label, label_pool, rng_component)
                source_particles = particles_by_sample[source_sample_id]
                base_count = len(source_particles)
                if base_count <= 0:
                    raise ValueError(f"source sample has no particles: {source_sample_id}")
                component_entries.append(
                    {
                        "component_id": component_id,
                        "label_fine": label,
                        "source_sample_id": source_sample_id,
                        "n_particles_source": base_count,
                    }
                )
                component_particles.append(source_particles)
                base_counts.append(base_count)

            alloc_counts = _allocate_particle_budget(
                base_counts,
                particle_budget_cfg,
                mode=particle_budget_mode,
            )

            sample_id = f"{sample_id_prefix}_{sample_idx:06d}"
            particle_id = 0
            for component_id, (label, source_particles, alloc_count) in enumerate(
                zip(labels, component_particles, alloc_counts)
            ):
                rng_subset = random.Random(_derive_seed(seed, sample_idx, f"compose_particles_{component_id}"))
                selected = _select_particles(source_particles, alloc_count, rng_subset)
                component_label_distribution[label] = component_label_distribution.get(label, 0) + 1
                component_entries[component_id]["n_particles"] = len(selected)
                for particle in selected:
                    row = dict(particle)
                    row["sample_id"] = sample_id
                    row["particle_id"] = particle_id
                    row["component_id"] = component_id
                    row["component_label_fine"] = str(label)
                    row["component"] = str(label)
                    particles_out.append(row)
                    particle_id += 1

            labels_fine = _unique_preserve(labels)
            primary_label = _primary_label(labels, alloc_counts)
            sample_row = {
                "sample_id": sample_id,
                "label": primary_label,
                "n_particles": particle_id,
                "pattern_params": json.dumps(
                    {
                        "compose": {
                            "components": component_entries,
                            "particle_budget": particle_budget_cfg,
                        }
                    },
                    sort_keys=True,
                    ensure_ascii=True,
                ),
                "seed_offset": sample_idx,
                "labels_fine": labels_fine,
                "label_fine_primary": primary_label,
                "components_json": json.dumps(component_entries, sort_keys=True, ensure_ascii=True),
            }
            samples_out.append(sample_row)
            compose_samples_manifest.append(
                {
                    "sample_id": sample_id,
                    "labels_fine": labels_fine,
                    "label_fine_primary": primary_label,
                    "n_particles": particle_id,
                    "components": component_entries,
                }
            )

        serialize_label_lists(samples_out, ["labels_fine"])
        validate_particles_table(particles_out)
        validate_samples_table(samples_out)

        io_cfg = _read_mapping(wp_cfg.get("io"), "wafer_particles.io")
        fmt_raw = str(io_cfg.get("format", "auto")).lower()
        fmt, auto_selected = _resolve_output_format(fmt_raw)
        if auto_selected:
            writer.log(f"io.format=auto resolved to {fmt}")
        csv_cfg = _read_mapping(io_cfg.get("csv"), "wafer_particles.io.csv", required=False)
        parquet_cfg = _read_mapping(io_cfg.get("parquet"), "wafer_particles.io.parquet", required=False)
        particles_path, samples_path = _data_paths(fmt)

        _write_table(
            writer.run_dir / particles_path,
            particles_out,
            fmt=fmt,
            csv_cfg=csv_cfg,
            parquet_cfg=parquet_cfg,
            columns=_columns_for_rows(particles_out, PARTICLES_SCHEMA),
        )
        _write_table(
            writer.run_dir / samples_path,
            samples_out,
            fmt=fmt,
            csv_cfg=csv_cfg,
            parquet_cfg=parquet_cfg,
            columns=_columns_for_rows(samples_out, SAMPLES_SCHEMA),
        )

        label_distribution = _label_distribution(samples_out)
        particle_label_distribution = _label_distribution(particles_out)
        manifest = build_manifest(
            particles_path=particles_path,
            samples_path=samples_path,
            particles_rows=len(particles_out),
            samples_rows=len(samples_out),
            label_distribution=label_distribution,
            schema_version=str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            domain=_domain_name(self.cfg),
        )
        writer.write_json("manifest.json", manifest)

        compose_manifest = {
            "schema_version": str(self.cfg.get("schema_version", SCHEMA_VERSION)),
            "domain": _domain_name(self.cfg),
            "input": input_payload(paths),
            "n_samples_out": n_samples_out,
            "sample_id_prefix": sample_id_prefix,
            "sample_id_format": f"{sample_id_prefix}_{{index:06d}}",
            "n_components": n_components_spec,
            "component_sampling": {
                "allow_duplicates": allow_duplicates,
                "weights": component_cfg.get("weights"),
            },
            "particle_budget": particle_budget_cfg,
            "samples": compose_samples_manifest,
        }
        writer.write_json("compose_manifest.json", compose_manifest)

        metrics = {
            "n_samples_out": n_samples_out,
            "n_particles": len(particles_out),
            "n_components_total": sum(len(entry["components"]) for entry in compose_samples_manifest),
            "sample_label_distribution": label_distribution,
            "particle_label_distribution": particle_label_distribution,
            "component_label_distribution": component_label_distribution,
            "input": input_payload(paths),
            "component_sampling": {
                "allow_duplicates": allow_duplicates,
                "weights": component_cfg.get("weights"),
            },
            "particle_budget": particle_budget_cfg,
        }
        writer.write_json("metrics/compose_summary.json", metrics)
        (writer.run_dir / "plots" / "placeholder.txt").write_text(
            "plots are not generated for process=compose\n",
            encoding="utf-8",
        )
        writer.log("compose complete")


def _resolve_wafer_particles_cfg(cfg: Mapping[str, Any]) -> dict[str, Any]:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        raise ValueError("wafer_particles config is required")
    return dict(wp_cfg)


def _read_mapping(value: Any, name: str, *, required: bool = True) -> dict[str, Any]:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _index_samples(samples: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in samples:
        sample_id = row.get("sample_id")
        if sample_id in (None, ""):
            raise ValueError("sample_id is required in samples")
        sample_id = str(sample_id)
        if sample_id in indexed:
            raise ValueError(f"duplicate sample_id in samples: {sample_id}")
        indexed[sample_id] = dict(row)
    return indexed


def _group_particles(
    particles: Sequence[Mapping[str, Any]],
    sample_ids: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {str(sample_id): [] for sample_id in sample_ids}
    for row in particles:
        sample_id = row.get("sample_id")
        if sample_id in (None, ""):
            raise ValueError("particle sample_id is required")
        sample_id = str(sample_id)
        if sample_id not in grouped:
            raise ValueError(f"particle sample_id missing from samples: {sample_id}")
        grouped[sample_id].append(dict(row))
    return grouped


def _sample_labels(samples_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for sample_id, row in samples_by_id.items():
        for key in ("label_fine_primary", "label_fine", "label"):
            value = row.get(key)
            if value not in (None, ""):
                labels[sample_id] = str(value)
                break
        if sample_id not in labels:
            raise ValueError(f"sample is missing label: {sample_id}")
    return labels


def _build_label_pool(labels_by_sample: Mapping[str, str]) -> dict[str, list[str]]:
    pool: dict[str, list[str]] = {}
    for sample_id, label in labels_by_sample.items():
        pool.setdefault(label, []).append(sample_id)
    for label, sample_ids in pool.items():
        sample_ids.sort()
        pool[label] = sample_ids
    return dict(sorted(pool.items(), key=lambda item: item[0]))


def _resolve_component_weights(
    weights_cfg: Any,
    label_pool: Mapping[str, Sequence[str]],
) -> tuple[list[str], list[float]]:
    labels = list(label_pool.keys())
    if not labels:
        raise ValueError("no labels available for compose")
    if weights_cfg is None:
        return labels, [1.0 for _ in labels]
    if not isinstance(weights_cfg, Mapping):
        raise ValueError("compose.component_sampling.weights must be a mapping")
    chosen_labels: list[str] = []
    weights: list[float] = []
    for label in labels:
        if label not in weights_cfg:
            continue
        weight = float(weights_cfg[label])
        if weight < 0:
            raise ValueError("compose.component_sampling.weights must be non-negative")
        if weight == 0:
            continue
        chosen_labels.append(label)
        weights.append(weight)
    if not chosen_labels:
        raise ValueError("compose.component_sampling.weights has no usable labels")
    return chosen_labels, weights


def _normalize_n_components_spec(spec: Any) -> dict[str, Any]:
    if isinstance(spec, bool):
        raise ValueError("compose.n_components must be an int or mapping")
    if isinstance(spec, int):
        return {"type": "fixed", "value": _coerce_positive_int(spec, "compose.n_components")}
    if not isinstance(spec, Mapping):
        raise ValueError("compose.n_components must be an int or mapping")
    spec = dict(spec)
    if "value" in spec:
        return {"type": "fixed", "value": _coerce_positive_int(spec["value"], "compose.n_components.value")}
    if "min" in spec and "max" in spec:
        return {
            "type": "range",
            "min": _coerce_positive_int(spec["min"], "compose.n_components.min"),
            "max": _coerce_positive_int(spec["max"], "compose.n_components.max"),
        }
    if "values" in spec:
        values = spec.get("values")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError("compose.n_components.values must be a list")
        parsed = [_coerce_positive_int(value, "compose.n_components.values") for value in values]
        weights = spec.get("weights")
        if weights is not None:
            if not isinstance(weights, Sequence) or isinstance(weights, (str, bytes)):
                raise ValueError("compose.n_components.weights must be a list")
            if len(weights) != len(parsed):
                raise ValueError("compose.n_components.weights length mismatch")
            weight_values = [float(weight) for weight in weights]
            if any(weight < 0 for weight in weight_values):
                raise ValueError("compose.n_components.weights must be non-negative")
        else:
            weight_values = None
        return {"type": "choice", "values": parsed, "weights": weight_values}
    raise ValueError("compose.n_components must set value, min/max, or values")


def _sample_n_components(spec: Mapping[str, Any], rng: random.Random) -> int:
    spec_type = spec.get("type")
    if spec_type == "fixed":
        return int(spec["value"])
    if spec_type == "range":
        min_value = int(spec["min"])
        max_value = int(spec["max"])
        if min_value > max_value:
            raise ValueError("compose.n_components.min must be <= max")
        return rng.randint(min_value, max_value)
    if spec_type == "choice":
        values = list(spec["values"])
        weights = spec.get("weights")
        if weights:
            return int(rng.choices(values, weights=weights, k=1)[0])
        return int(rng.choice(values))
    raise ValueError(f"unsupported n_components type: {spec_type}")


def _resolve_particle_budget_mode(cfg: Mapping[str, Any]) -> str:
    mode = str(cfg.get("mode", "all")).lower()
    if mode in {"all", "fixed_total", "per_component"}:
        return mode
    raise ValueError(f"unsupported particle_budget.mode: {mode}")


def _allocate_particle_budget(
    base_counts: Sequence[int],
    cfg: Mapping[str, Any],
    *,
    mode: str,
) -> list[int]:
    if not base_counts:
        return []
    if mode == "all":
        return [int(count) for count in base_counts]
    if mode == "per_component":
        per_component = _coerce_positive_int(cfg.get("per_component"), "compose.particle_budget.per_component")
        return [min(per_component, int(count)) for count in base_counts]
    if mode == "fixed_total":
        total = _coerce_positive_int(cfg.get("total"), "compose.particle_budget.total")
        strategy = str(cfg.get("strategy", "proportional")).lower()
        if strategy != "proportional":
            raise ValueError("compose.particle_budget.strategy must be proportional")
        total_available = sum(int(count) for count in base_counts)
        if total >= total_available:
            return [int(count) for count in base_counts]
        if total < len(base_counts):
            raise ValueError("compose.particle_budget.total must be >= n_components")
        base = [1 for _ in base_counts]
        remaining = total - len(base_counts)
        capacities = [max(0, int(count) - 1) for count in base_counts]
        if remaining <= 0:
            return base
        if remaining >= sum(capacities):
            return [int(count) for count in base_counts]
        extras = _allocate_proportional(remaining, capacities)
        return [base[idx] + extras[idx] for idx in range(len(base_counts))]
    raise ValueError(f"unsupported particle_budget.mode: {mode}")


def _allocate_proportional(total: int, weights: Sequence[int]) -> list[int]:
    if total <= 0:
        return [0 for _ in weights]
    total_weight = sum(weights)
    if total_weight <= 0:
        return [0 for _ in weights]
    raw = [total * weight / total_weight for weight in weights]
    counts = [int(value) for value in raw]
    remainder = total - sum(counts)
    if remainder <= 0:
        return counts
    fractions = [value - int(value) for value in raw]
    order = sorted(range(len(fractions)), key=lambda idx: (-fractions[idx], idx))
    for idx in range(remainder):
        counts[order[idx]] += 1
    return counts


def _sample_component_labels(
    rng: random.Random,
    labels: Sequence[str],
    weights: Sequence[float],
    n_components: int,
    *,
    allow_duplicates: bool,
) -> list[str]:
    if n_components <= 0:
        raise ValueError("compose.n_components must be positive")
    if not allow_duplicates:
        if n_components > len(labels):
            raise ValueError("compose.n_components exceeds available labels")
        remaining_labels = list(labels)
        remaining_weights = list(weights)
        chosen: list[str] = []
        for _ in range(n_components):
            label = _weighted_choice(rng, remaining_labels, remaining_weights)
            idx = remaining_labels.index(label)
            remaining_labels.pop(idx)
            remaining_weights.pop(idx)
            chosen.append(label)
        return chosen
    return [rng.choices(labels, weights=weights, k=1)[0] for _ in range(n_components)]


def _weighted_choice(rng: random.Random, labels: Sequence[str], weights: Sequence[float]) -> str:
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("component_sampling weights must sum to > 0")
    pick = rng.random() * total_weight
    cumulative = 0.0
    for label, weight in zip(labels, weights):
        cumulative += weight
        if pick <= cumulative:
            return label
    return str(labels[-1])


def _choose_source_sample(
    label: str,
    label_pool: Mapping[str, Sequence[str]],
    rng: random.Random,
) -> str:
    sample_ids = label_pool.get(label)
    if not sample_ids:
        raise ValueError(f"no samples available for label: {label}")
    return str(rng.choice(list(sample_ids)))


def _select_particles(
    particles: Sequence[Mapping[str, Any]],
    count: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    if count >= len(particles):
        return [dict(row) for row in particles]
    indices = list(range(len(particles)))
    rng.shuffle(indices)
    chosen = sorted(indices[:count])
    return [dict(particles[idx]) for idx in chosen]


def _unique_preserve(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _primary_label(labels: Sequence[str], counts: Sequence[int]) -> str:
    if not labels:
        raise ValueError("no labels available for primary selection")
    totals: dict[str, int] = {}
    for label, count in zip(labels, counts):
        totals[label] = totals.get(label, 0) + int(count)
    ordered = _unique_preserve(labels)
    best_label = ordered[0]
    best_count = totals.get(best_label, 0)
    for label in ordered[1:]:
        count = totals.get(label, 0)
        if count > best_count:
            best_label = label
            best_count = count
    return str(best_label)


def _label_distribution(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for row in rows:
        label = row.get("label")
        if label is None:
            continue
        key = str(label)
        dist[key] = dist.get(key, 0) + 1
    return dist


def _columns_for_rows(rows: Sequence[Mapping[str, Any]], schema) -> list[str]:
    preferred = [spec.name for spec in schema.required] + [spec.name for spec in schema.optional]
    keys: set[str] = set()
    for row in rows:
        keys.update(str(key) for key in row.keys())
    columns: list[str] = [name for name in preferred if name in keys]
    columns.extend(sorted(keys - set(columns)))
    if not columns:
        return list(preferred)
    return columns


def _resolve_output_format(fmt: str) -> tuple[str, bool]:
    if fmt != "auto":
        return fmt, False
    try:
        import pyarrow  # noqa: F401
    except Exception:
        return "csv", True
    return "parquet", True


def _data_paths(fmt: str) -> tuple[str, str]:
    if fmt == "csv":
        return ("data/particles.csv", "data/samples.csv")
    if fmt == "parquet":
        return ("data/particles.parquet", "data/samples.parquet")
    raise ValueError(f"unsupported io.format: {fmt}")


def _write_table(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fmt: str,
    csv_cfg: Mapping[str, Any],
    parquet_cfg: Mapping[str, Any],
    columns: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        _write_csv(path, rows, columns, csv_cfg)
        return
    if fmt == "parquet":
        _write_parquet(path, rows, columns, parquet_cfg)
        return
    raise ValueError(f"unsupported io.format: {fmt}")


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    cfg: Mapping[str, Any],
) -> None:
    delimiter = str(cfg.get("delimiter", ","))
    quotechar = str(cfg.get("quotechar", '"'))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(columns),
            extrasaction="ignore",
            delimiter=delimiter,
            quotechar=quotechar,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_parquet(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    cfg: Mapping[str, Any],
) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception as exc:
        raise RuntimeError(
            "pyarrow is required for parquet output (set wafer_particles.io.format=csv to use CSV)."
        ) from exc
    data = {col: [row.get(col) for row in rows] for col in columns}
    table = pa.Table.from_pydict(data)
    compression = cfg.get("compression") if cfg else None
    pq.write_table(table, path, compression=compression)


def _domain_name(cfg: Mapping[str, Any]) -> str:
    domain = cfg.get("domain")
    if isinstance(domain, Mapping) and domain.get("name"):
        return str(domain["name"])
    if domain:
        return str(domain)
    return DOMAIN_NAME


def _derive_seed(base_seed: int, offset: int, component: str) -> int:
    payload = f"{base_seed}:{offset}:{component}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(base_seed) + int(digest[:12], 16)


def _coerce_positive_int(value: Any, name: str) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an int")
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _coerce_int(value: Any, name: str) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an int")
