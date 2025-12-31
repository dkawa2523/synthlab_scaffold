# TASK: T0503 Pattern engine refactor (base interface, registry, geometry/masks primitives) (P0)

## Why
- 21 patterns will cause if/else explosion unless we enforce:
  - single interface
  - shared geometry/mask primitives
  - shared param sampling
- Ensures multiple developers can add patterns safely.

## Contracts
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/11_PLUGIN_REGISTRY.md
- docs/10_PROCESS_CATALOG.md

## Scope
1) Introduce a pattern interface:
   - `Pattern.generate(ctx, params, rng) -> particles_df`
   - `Pattern.meta() -> {pattern_id, touch_edge, internal_only, tags...}`
   - `Pattern.params_schema()` for docs/validation (lightweight)
   - Ensure all patterns output consistent schema:
     - particle columns: `sample_id, r_norm, theta_rad, r_mm, size_um, label_fine`
     - (optional for composite) `component_id, component_label_fine`

2) Add a registry/catalog:
   - `pattern_id -> Pattern implementation`
   - Config-driven enable/disable:
     - `conf/wafer_particles/patterns/<pattern_id>.yaml` includes `enabled: true/false`
   - A central catalog loader used by generate:
     - lists enabled patterns and their configs

3) Shared primitives modules:
   - `geometry.py`:
     - sample in disk/annulus
     - wedge/sector sampling (including von Mises trunc + radial beta)
     - radial lines (with width and length)
     - straight line segment (with width and length)
     - periodic scratches (line repetition)
     - curved scratch (arc)
     - spiral
     - hotspot iso/elliptic
     - edge point-source spray/bursty
   - `masks.py`:
     - ring segment masks, arc-band masks, donut/annulus masks
     - crescent (edge/internal) region definition
   - Everything operates in normalized coords (r_norm in [0,1]) internally.

4) Backward compatibility:
   - Keep existing `process=generate/qc/viz/export` entry points unchanged.
   - If old config keys exist, add a compatibility mapping (warn + translate).

## Acceptance Criteria
- [ ] A new pattern can be added by adding a single python file + YAML + registry entry, without touching unrelated code.
- [ ] Patterns share primitives; no copy-pasted geometry code.
- [ ] All particles are guaranteed to lie within wafer disk (doctor + runtime asserts).
- [ ] Normalized coords are standard and mm is derived from wafer radius.

## Implementation Notes
- Keep geometry functions pure and testable (no file I/O).
- Use `param_space` from T0502 everywhere.

## Verification
- Add `tests/test_T0503_pattern_engine_smoke.py`
  - Load catalog, instantiate a few patterns, generate particles, assert schema and bounds.
