# 14_LABELING_AND_GROUPS - Labeling layers & similarity groups

## 1. Concepts
- Phenotype (fine label): the generator pattern_id (stored as `label` / `label_fine`).
- Derived layers: label layers computed from the external spec (e.g. `label_family`, `label_location`).
- Cause hypotheses: optional metadata for human review; NOT ground-truth labels.

## 2. External labeling spec (YAML)
The labeling spec lives outside code and is loaded at runtime.

Config entry:
- `wafer_particles.labeling.spec_path` (default: `conf/wafer_particles/labeling/label_layers_example_v1.yaml`)

Process flow:
- `process=labeling_apply` loads the spec and writes:
  - `meta/labeling_spec.yaml`
  - `meta/labeling_spec_hash.txt`
  - `reports/labeling_layers_summary.json`
  - `reports/similarity_groups_summary.json`

Minimal override example:
```bash
python -m synthlab.cli.main process=labeling_apply seed=7 run_name=labeling_demo \
  wafer_particles.labeling.spec_path=path/to/labeling_spec.yaml \
  wafer_particles.labeling_apply.input.run_name=export_run_name
```

## 3. Similarity group reference (current labels)
Recommended similarity groups (reference list; adjust with your taxonomy updates):
- Edge-origin / edge-contact: C02_EdgeBiased, C04_Sector_Edge, K03_Edge_Arc, C12_Crescent_Edge, C14_EdgeSource_Spray, C15_EdgeSource_Bursty
- Radial band family: C03_Ring, K01_Donut_Hollow, K02_SemiRing_Segment, K03_Edge_Arc
- Line/scratch family: C06_RadialLines, C07_StraightLine, K04_Scratch_Periodic, C08_CurvedScratch
- Local cluster family: C10_Hotspot_Iso, C11_Hotspot_Elliptic
- Periodic / non-particle candidates: O01_ReticleRepeat, O02_Checkerboard

## 4. Notes
- Keep the spec aligned with `conf/wafer_particles/labels/*` or your external taxonomy.
- Cause hypotheses are metadata only; do not use as supervised targets without validation.
