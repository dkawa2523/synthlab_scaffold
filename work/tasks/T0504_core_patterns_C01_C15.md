# TASK: T0504 Implement Core patterns C01–C15 (P0)

## Why
- Implements the agreed rule-based pattern set for particle deposition analysis.

## Contracts
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/11_PLUGIN_REGISTRY.md

## Scope
Implement pattern generators and Hydra configs for:
- C01 Uniform
- C02 EdgeBiased
- C03 Ring
- C04 Sector_Edge (non-uniform angular/radial distributions)
- C05 Sector_Internal (non-uniform; must not touch edge by default)
- C06 RadialLines (length/width configurable)
- C07 StraightLine (length/width configurable)
- C08 CurvedScratch (arc length/width configurable)
- C09 Spiral (turns/width configurable)
- C10 Hotspot_Iso
- C11 Hotspot_Elliptic (anisotropic gaussian; separate label)
- C12 Crescent_Edge
- C13 Crescent_Internal
- C14 EdgeSource_Spray
- C15 EdgeSource_Bursty

For each:
- Add `conf/wafer_particles/patterns/<pattern_id>.yaml`
  - Must allow continuous parameter sampling via `param_space` specs.
  - Must include `enabled` and sensible defaults.
- Ensure outputs include `label_fine = pattern_id`.

## Acceptance Criteria
- [ ] All C01–C15 are registered and selectable via Hydra.
- [ ] Sector patterns support non-uniform distributions (angle: von Mises trunc; radius: beta trunc) and are reproducible by seed.
- [ ] Hotspot_Elliptic exists as a separate fine label and supports rotation angle.
- [ ] Edge vs Internal variants are enforced by parameter constraints (doctor + runtime).
- [ ] Each pattern has at least one test asserting a characteristic property.

## Implementation Notes
- Keep patterns internal math in normalized coordinates.
- Ensure line-like patterns include parameters for **length and width**:
  - StraightLine: segment_half_length_norm, width_norm
  - RadialLines: r_min_norm/r_max_norm, sigma_perp_norm
  - CurvedScratch: arc_radius_norm, span_rad, width_norm
  - Spiral: theta_max, width_norm

## Verification
- Add `tests/test_T0504_core_patterns_properties.py`
  - Generate each pattern with a fixed seed and assert:
    - bounds within wafer
    - simple property checks (e.g., edge patterns mean r_norm high; internal sector max r_norm < 1.0 - margin; ellipse hotspot covariance anisotropy)
