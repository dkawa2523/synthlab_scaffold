# TASK: T0505 Implement Keep patterns K01–K04 + Optional patterns O01–O02 (P0)

## Why
- Even if mask-based, these patterns correspond to different suspected mechanisms and should remain as fine labels.
- Optional periodic patterns are kept disabled by default to avoid polluting “pure particle” datasets.

## Contracts
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/11_PLUGIN_REGISTRY.md

## Scope
Implement and register:
- K01 Donut_Hollow
- K02 SemiRing_Segment
- K03 Edge_Arc
- K04 Scratch_Periodic (periodic multi-line scratch; spacing/band-count configurable)
- O01 ReticleRepeat (optional, enabled=false by default)
- O02 Checkerboard (optional, enabled=false by default)

Add YAML configs under `conf/wafer_particles/patterns/`.

## Acceptance Criteria
- [ ] K01–K04 exist as separate fine labels, even if implemented via shared mask primitives.
- [ ] O01/O02 exist but are disabled by default (doctor warns if enabled without explicit override).
- [ ] Scratch_Periodic supports continuous spacing and phase/random offset (avoid over-regular synthetic).
- [ ] Each pattern has a basic test.

## Implementation Notes
- For O01/O02, document that they may represent stepper/reticle or measurement artifacts, not deposition.
- Keep O patterns isolated by default dataset profile or config preset.

## Verification
- Add `tests/test_T0505_keep_optional_patterns.py`
  - Ensure patterns load and generate
  - Assert `enabled=false` by default for optional patterns
