from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import yaml

from synthlab.framework.artifacts import ensure_unique_run_name
from synthlab.framework.process import dispatch_process

# Register processes
import synthlab.processes  # noqa: F401


def _coerce_value(raw: str) -> Any:
    lower = raw.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none"}:
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _set_nested(target: dict[str, Any], keys: list[str], value: Any) -> None:
    cur = target
    for key in keys[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = value


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _deep_fill(base: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        if key not in base:
            base[key] = value
        elif isinstance(base.get(key), dict) and isinstance(value, dict):
            _deep_fill(base[key], value)
    return base


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing config file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return data


def _wrap_group(group: str, content: dict[str, Any]) -> dict[str, Any]:
    wrapped: dict[str, Any] = content
    for key in reversed(group.split("/")):
        wrapped = {key: wrapped}
    return wrapped


def _parse_default_string(item: str) -> tuple[str, str]:
    if "/" not in item:
        raise ValueError(f"unsupported defaults entry: {item}")
    group, option = item.rsplit("/", 1)
    if not group or not option:
        raise ValueError(f"invalid defaults entry: {item}")
    return group, option


def _compose_group(conf_root: Path, group: str, option: str) -> dict[str, Any]:
    path = conf_root / group / f"{option}.yaml"
    content = _compose_from_file(path, conf_root)
    return _wrap_group(group, content)


def _compose_from_file(path: Path, conf_root: Path) -> dict[str, Any]:
    data = _load_yaml(path)
    defaults = data.pop("defaults", [])
    if defaults is None:
        defaults = []
    if not isinstance(defaults, list):
        raise ValueError(f"defaults must be a list: {path}")
    composed: dict[str, Any] = {}
    merged_self = False
    for item in defaults:
        if item == "_self_":
            _deep_update(composed, data)
            merged_self = True
            continue
        if isinstance(item, str):
            if item.startswith("override "):
                continue
            group, option = _parse_default_string(item)
            _deep_update(composed, _compose_group(conf_root, group, option))
            continue
        if isinstance(item, dict):
            for group, option in item.items():
                if group.startswith("override "):
                    continue
                if option is None:
                    raise ValueError(f"defaults entry missing option: {group}")
                _deep_update(composed, _compose_group(conf_root, group, str(option)))
            continue
        raise ValueError(f"defaults entries must be mappings or strings: {path}")
    if not merged_self:
        _deep_update(composed, data)
    return composed


def _parse_overrides(overrides: list[str]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    parsed: dict[str, Any] = {}
    group_overrides: list[tuple[str, str]] = []
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"override must be key=value: {item}")
        key, raw = item.split("=", 1)
        if not key:
            raise ValueError(f"override key is empty: {item}")
        if "/" in key:
            group_overrides.append((key, raw))
            continue
        _set_nested(parsed, key.split("."), _coerce_value(raw))
    return parsed, group_overrides


def _default_run_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return f"{ts}_{uuid.uuid4().hex[:6]}"


def _load_group_content(conf_root: Path, group: str, option: str) -> dict[str, Any] | None:
    path = conf_root / group / f"{option}.yaml"
    if not path.exists():
        return None
    return _compose_from_file(path, conf_root)


def _normalize_process(cfg: dict[str, Any], conf_root: Path) -> None:
    proc = cfg.get("process")
    if isinstance(proc, str):
        group_cfg = _load_group_content(conf_root, "process", proc)
        if group_cfg is None:
            cfg["process"] = {"name": proc}
            return
        proc_cfg = dict(group_cfg)
        proc_name = proc_cfg.pop("name", proc)
        if proc_cfg:
            _deep_fill(cfg, proc_cfg)
        cfg["process"] = {"name": proc_name}
    elif isinstance(proc, dict):
        if "name" not in proc or not proc["name"]:
            raise ValueError("process.name is required")
    else:
        raise ValueError("process is required")


def _normalize_domain(cfg: dict[str, Any], conf_root: Path) -> None:
    domain = cfg.get("domain")
    if isinstance(domain, str):
        group_cfg = _load_group_content(conf_root, "domain", domain)
        cfg["domain"] = group_cfg if group_cfg is not None else domain
    elif isinstance(domain, dict):
        if "name" not in domain or not domain["name"]:
            raise ValueError("domain.name is required")
    else:
        raise ValueError("domain is required")


def _is_missing(value: Any) -> bool:
    return value is None or value == "???"


def _render_now_template(value: str) -> str | None:
    prefix = "${now:"
    if not value.startswith(prefix) or not value.endswith("}"):
        return None
    fmt = value[len(prefix) : -1]
    if not fmt:
        return None
    return datetime.now(timezone.utc).strftime(fmt)


def _normalize_run_name(cfg: dict[str, Any]) -> None:
    run_name = cfg.get("run_name")
    if not run_name or _is_missing(run_name):
        cfg["run_name"] = _default_run_name()
        return
    if isinstance(run_name, str):
        rendered = _render_now_template(run_name)
        if rendered:
            cfg["run_name"] = rendered


def _ensure_seed(cfg: dict[str, Any]) -> None:
    if _is_missing(cfg.get("seed")):
        raise ValueError("seed is required")


def _ensure_schema_version(cfg: dict[str, Any]) -> None:
    if not _is_missing(cfg.get("schema_version")):
        return
    domain = cfg.get("domain")
    if isinstance(domain, dict) and domain.get("schema_version"):
        cfg["schema_version"] = domain["schema_version"]
        return
    raise ValueError("schema_version is required")


def _apply_group_overrides(
    cfg: dict[str, Any],
    group_overrides: list[tuple[str, str]],
    conf_root: Path,
) -> None:
    for group, option in group_overrides:
        if not option:
            raise ValueError(f"group override missing option: {group}")
        _deep_update(cfg, _compose_group(conf_root, group, option))


def _resolve_profile_cfg(cfg: Mapping[str, Any]) -> dict[str, Any] | None:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        return None
    profile_cfg = wp_cfg.get("profiles")
    if not isinstance(profile_cfg, Mapping):
        return None
    return dict(profile_cfg)


def _apply_profile_overrides(cfg: dict[str, Any]) -> None:
    profile_cfg = _resolve_profile_cfg(cfg)
    if not profile_cfg:
        return
    overrides = profile_cfg.get("overrides")
    if overrides is None:
        return
    if not isinstance(overrides, Mapping):
        raise ValueError("wafer_particles.profiles.overrides must be a mapping")
    _deep_update(cfg, dict(overrides))


def _apply_size_model_defaults(cfg: dict[str, Any]) -> None:
    wp_cfg = cfg.get("wafer_particles")
    if not isinstance(wp_cfg, Mapping):
        return
    defaults_cfg = wp_cfg.get("size_model_defaults")
    if not isinstance(defaults_cfg, Mapping):
        return
    clamp_cfg = defaults_cfg.get("clamp_um")
    if clamp_cfg is None:
        return
    if not isinstance(clamp_cfg, Mapping):
        raise ValueError("wafer_particles.size_model_defaults.clamp_um must be a mapping")
    clamp_min = _coerce_optional_float(clamp_cfg.get("min", clamp_cfg.get("min_um")), "clamp_um.min")
    clamp_max = _coerce_optional_float(clamp_cfg.get("max", clamp_cfg.get("max_um")), "clamp_um.max")
    if clamp_min is None and clamp_max is None:
        return
    size_cfg = wp_cfg.get("size_models") or wp_cfg.get("size_model")
    if not isinstance(size_cfg, Mapping):
        return
    _apply_size_model_clamp(size_cfg, clamp_min, clamp_max)


def _apply_size_model_clamp(cfg: Mapping[str, Any], clamp_min: float | None, clamp_max: float | None) -> None:
    if clamp_min is not None:
        cfg["min_um"] = clamp_min
    if clamp_max is not None:
        cfg["max_um"] = clamp_max
    by_label = cfg.get("by_label")
    if isinstance(by_label, Mapping):
        for label_cfg in by_label.values():
            if isinstance(label_cfg, Mapping):
                _apply_size_model_clamp(label_cfg, clamp_min, clamp_max)
    components = cfg.get("components")
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, Mapping):
                continue
            component_cfg = component.get("cfg")
            if isinstance(component_cfg, Mapping):
                _apply_size_model_clamp(component_cfg, clamp_min, clamp_max)


def _coerce_optional_float(value: Any, name: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc


def resolve_config(
    overrides: dict[str, Any],
    repo_root: Path,
    *,
    group_overrides: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    conf_root = repo_root / "conf"
    cfg = _compose_from_file(conf_root / "config.yaml", conf_root)
    if group_overrides:
        _apply_group_overrides(cfg, group_overrides, conf_root)
    _apply_profile_overrides(cfg)
    _deep_update(cfg, overrides)
    _normalize_domain(cfg, conf_root)
    _normalize_process(cfg, conf_root)
    _normalize_run_name(cfg)
    _ensure_seed(cfg)
    _ensure_schema_version(cfg)
    _apply_size_model_defaults(cfg)
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SynthLab CLI (minimal dispatcher)",
    )
    parser.add_argument(
        "overrides",
        nargs="*",
        help="Hydra-style overrides, e.g. process=doctor seed=1",
    )
    args = parser.parse_args(argv)

    overrides = list(args.overrides)
    try:
        override_cfg, group_overrides = _parse_overrides(overrides)
        cfg = resolve_config(override_cfg, repo_root=Path.cwd(), group_overrides=group_overrides)
        process_name = cfg["process"]["name"]
        runs_dir = Path.cwd() / "runs"
        cfg["run_name"] = ensure_unique_run_name(runs_dir, str(cfg["run_name"]), process_name)
        dispatch_process(cfg=cfg, overrides=overrides, repo_root=Path.cwd())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
