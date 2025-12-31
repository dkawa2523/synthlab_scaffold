# 12_COMPOSITE_DSL — Composite Pattern DSL (v1)

## Overview
- composite pattern is driven by a YAML `components` list.
- each component can override pattern config and apply a polar transform.

## DSL
```
components:
  - pattern: wafer_particles.pattern.ring_narrow
    weight: 0.6
    label: ring        # optional (defaults to pattern key)
    cfg:
      radius_ratio: 0.7
      width_ratio: 0.03
    transform:
      rotate_theta_rad: 0.3
      mirror_theta: false
      radial_scale: 0.8
      theta_jitter_std: 0.02
      r_jitter_std: 0.4
```

## Transform rules
- applied in polar space; order is: radial_scale -> rotate -> mirror -> jitter -> clamp.
- r is clamped to `[0, wafer_radius_mm]`, theta is normalized to `[0, 2pi)`.

## Range values
- `rotate_theta_rad` and `radial_scale` accept a constant or a range.
- supported range forms:
  - list: `[min, max]`
  - mapping: `{min: <val>, max: <val>}`

## Presets
- see `conf/wafer_particles/patterns/composite_*.yaml` for examples.
