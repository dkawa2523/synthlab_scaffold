from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class PatternCatalogEntry:
    label_fine: str
    pattern_id: str
    cfg: dict[str, Any]
    enabled: bool


@dataclass(frozen=True)
class PatternCatalog:
    entries: dict[str, PatternCatalogEntry]

    def enabled_entries(self) -> dict[str, PatternCatalogEntry]:
        return {label: entry for label, entry in self.entries.items() if entry.enabled}

    def enabled_configs(self) -> dict[str, dict[str, Any]]:
        return {label: dict(entry.cfg) for label, entry in self.enabled_entries().items()}


def load_pattern_catalog(
    wp_cfg: Mapping[str, Any],
    *,
    warn: Callable[[str], None] | None = None,
) -> PatternCatalog:
    patterns = wp_cfg.get("patterns")
    if not isinstance(patterns, Mapping):
        raise ValueError("wafer_particles.patterns must be a mapping")
    warn_fn = warn or (lambda message: None)
    entries: dict[str, PatternCatalogEntry] = {}
    for label, cfg in patterns.items():
        if not isinstance(cfg, Mapping):
            raise ValueError(f"pattern config for {label} must be a mapping")
        label_fine = str(label)
        resolved = dict(cfg)
        enabled = bool(resolved.pop("enabled", True))
        pattern_id = _resolve_pattern_id(resolved, label_fine, warn_fn)
        entries[label_fine] = PatternCatalogEntry(
            label_fine=label_fine,
            pattern_id=pattern_id,
            cfg=resolved,
            enabled=enabled,
        )
    if not entries:
        raise ValueError("wafer_particles.patterns is empty")
    return PatternCatalog(entries=entries)


def _resolve_pattern_id(
    cfg: dict[str, Any],
    label: str,
    warn_fn: Callable[[str], None],
) -> str:
    pattern_id = cfg.get("name")
    if pattern_id:
        return str(pattern_id)
    legacy = cfg.get("pattern_id") or cfg.get("pattern")
    if legacy:
        warn_fn(f"pattern config for {label} uses legacy key; mapping to name")
        cfg["name"] = legacy
        return str(legacy)
    raise ValueError(f"pattern name is required for label {label}")
