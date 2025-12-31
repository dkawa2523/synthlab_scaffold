from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

PATTERN_PARAMS_SCHEMA_VERSION = "wafer_particles.pattern_params.v1"


@dataclass(frozen=True)
class PatternContext:
    n_particles: int
    wafer_radius_mm: float


@dataclass(frozen=True)
class PatternMeta:
    pattern_id: str
    touch_edge: bool = False
    internal_only: bool = False
    tags: tuple[str, ...] = ()


class PatternBase:
    pattern_id: str = ""
    touch_edge: bool = False
    internal_only: bool = False
    tags: Sequence[str] = ()

    @classmethod
    def meta(cls) -> PatternMeta:
        if not cls.pattern_id:
            raise ValueError("pattern_id is required")
        return PatternMeta(
            pattern_id=cls.pattern_id,
            touch_edge=bool(cls.touch_edge),
            internal_only=bool(cls.internal_only),
            tags=tuple(str(tag) for tag in cls.tags),
        )

    @classmethod
    def params_schema(cls) -> Mapping[str, Any]:
        return {
            "schema_version": PATTERN_PARAMS_SCHEMA_VERSION,
            "pattern_id": cls.pattern_id,
            "params": {},
        }

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
