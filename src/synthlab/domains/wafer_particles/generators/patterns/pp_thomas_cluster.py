from __future__ import annotations

from typing import Any, Mapping

from synthlab.framework.registry import register_pattern

from .base import PatternBase, PatternContext
from .cluster_parent_child import ClusterParentChild


@register_pattern("wafer_particles.pattern.pp_thomas_cluster")
class PpThomasCluster(PatternBase):
    pattern_id = "wafer_particles.pattern.pp_thomas_cluster"
    tags = ("cluster",)

    @classmethod
    def generate(
        cls,
        ctx: PatternContext,
        params: Mapping[str, Any],
        rng: Any,
    ) -> list[dict[str, Any]]:
        return ClusterParentChild.generate(ctx, params, rng)
