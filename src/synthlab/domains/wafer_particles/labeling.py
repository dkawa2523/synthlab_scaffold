from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

UNKNOWN_LABEL = "UNKNOWN"


def sanitize_layer_name(name: str) -> str:
    raw = str(name).strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    if not raw:
        raw = "layer"
    if raw[0].isdigit():
        raw = f"layer_{raw}"
    return raw


def normalize_label_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            parsed = _try_parse_json_list(text)
            if parsed is not None:
                return parsed
            inner = text[1:-1].strip()
            if not inner:
                return []
            items = [item.strip().strip('"').strip("'") for item in inner.split(",")]
            return [item for item in items if item]
        return [text]
    return [str(value)]


def _try_parse_json_list(text: str) -> list[str] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return [str(item) for item in parsed if item not in (None, "")]


def serialize_label_lists(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> None:
    for row in rows:
        for column in columns:
            if column not in row:
                continue
            value = row.get(column)
            labels = normalize_label_list(value)
            row[column] = json.dumps(labels, ensure_ascii=True)


def _unique_preserve(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _read_fine_label(row: Mapping[str, Any]) -> str | None:
    value = row.get("label_fine")
    if value in (None, ""):
        value = row.get("label")
    if value in (None, ""):
        return None
    return str(value)


def _map_label(value: Any, mapping: Mapping[str, str]) -> str:
    if value in (None, ""):
        return UNKNOWN_LABEL
    key = str(value)
    return mapping.get(key, UNKNOWN_LABEL)


@dataclass(frozen=True)
class LabelingSpec:
    raw: dict[str, Any]
    layers: dict[str, dict[str, str]]
    similarity_groups: list[dict[str, Any]]
    cause_hypotheses: dict[str, dict[str, Any]]
    layer_columns: dict[str, str]

    @classmethod
    def load(cls, path: str | Path) -> "LabelingSpec":
        spec_path = Path(path)
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError(f"labeling spec must be a mapping: {spec_path}")
        layers = _parse_layers(data.get("layers"))
        layer_columns = _sanitize_layer_columns(layers.keys())
        similarity_groups = _parse_similarity_groups(data.get("similarity_groups"))
        cause_hypotheses = _parse_cause_hypotheses(data.get("cause_hypotheses"))
        return cls(
            raw=data,
            layers=layers,
            similarity_groups=similarity_groups,
            cause_hypotheses=cause_hypotheses,
            layer_columns=layer_columns,
        )

    def hash(self) -> str:
        dumped = yaml.safe_dump(self.raw, sort_keys=True, allow_unicode=False)
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.raw, sort_keys=True, allow_unicode=False)

    def apply_to_particles(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows or not self.layers:
            return rows
        for row in rows:
            fine_label = _read_fine_label(row)
            for layer_name, mapping in self.layers.items():
                col = f"label_{self.layer_columns[layer_name]}"
                row[col] = _map_label(fine_label, mapping)
        return rows

    def apply_to_samples(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows or not self.layers:
            return rows
        has_labels_fine = any("labels_fine" in row for row in rows)
        has_primary = any("label_fine_primary" in row for row in rows)
        for row in rows:
            fine_label = _read_fine_label(row)
            for layer_name, mapping in self.layers.items():
                col = f"label_{self.layer_columns[layer_name]}"
                row[col] = _map_label(fine_label, mapping)
            if has_labels_fine:
                labels_fine = normalize_label_list(row.get("labels_fine"))
                for layer_name, mapping in self.layers.items():
                    col = f"labels_{self.layer_columns[layer_name]}"
                    mapped = [_map_label(label, mapping) for label in labels_fine]
                    row[col] = _unique_preserve(mapped)
            if has_primary:
                primary = row.get("label_fine_primary")
                for layer_name, mapping in self.layers.items():
                    col = f"label_{self.layer_columns[layer_name]}_primary"
                    row[col] = _map_label(primary, mapping)
        return rows


def _parse_layers(value: Any) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("labeling.layers must be a mapping")
    layers: dict[str, dict[str, str]] = {}
    for layer_name, mapping in value.items():
        if not isinstance(mapping, Mapping):
            raise ValueError(f"labeling.layers.{layer_name} must be a mapping")
        resolved: dict[str, str] = {}
        for key, derived in mapping.items():
            derived_value = UNKNOWN_LABEL if derived in (None, "") else str(derived)
            resolved[str(key)] = derived_value
        layers[str(layer_name)] = resolved
    return layers


def _sanitize_layer_columns(layer_names: Sequence[str]) -> dict[str, str]:
    columns: dict[str, str] = {}
    used: dict[str, str] = {}
    for name in layer_names:
        safe = sanitize_layer_name(name)
        if safe in used and used[safe] != name:
            raise ValueError(f"labeling layer name collision: {used[safe]} vs {name}")
        used[safe] = name
        columns[name] = safe
    return columns


def _parse_similarity_groups(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("labeling.similarity_groups must be a list")
    groups: list[dict[str, Any]] = []
    for idx, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ValueError(f"labeling.similarity_groups[{idx}] must be a mapping")
        name = entry.get("name") or f"group_{idx}"
        description = entry.get("description") or ""
        members_raw = entry.get("members") or []
        if not isinstance(members_raw, Sequence) or isinstance(members_raw, (str, bytes)):
            raise ValueError(f"labeling.similarity_groups[{idx}].members must be a list")
        members = [str(item) for item in members_raw if item not in (None, "")]
        groups.append(
            {
                "name": str(name),
                "description": str(description),
                "members": members,
            }
        )
    return groups


def _parse_cause_hypotheses(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("labeling.cause_hypotheses must be a mapping")
    causes: dict[str, dict[str, Any]] = {}
    for cause_id, payload in value.items():
        if not isinstance(payload, Mapping):
            raise ValueError(f"labeling.cause_hypotheses.{cause_id} must be a mapping")
        related_raw = payload.get("related_labels") or []
        if not isinstance(related_raw, Sequence) or isinstance(related_raw, (str, bytes)):
            raise ValueError(
                f"labeling.cause_hypotheses.{cause_id}.related_labels must be a list"
            )
        causes[str(cause_id)] = {
            "title": str(payload.get("title") or ""),
            "description": str(payload.get("description") or ""),
            "confidence": str(payload.get("confidence") or ""),
            "related_labels": [str(item) for item in related_raw if item not in (None, "")],
        }
    return causes
