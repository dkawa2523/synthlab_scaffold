# Dataset Card

## Overview
- dataset_id: wafer_particles.v1_taxonomy_v1_d0f341a6059f
- domain: wafer_particles
- schema_version: wafer_particles.v1
- taxonomy_version: taxonomy_v1
- created_at: 2025-12-31T22:34:44.088454+00:00

## Config
- config_hash: 3225d80c1bcd
- dataset_config_hash: a5337615bd89
- input_config_hash: e32d6f3513e2

## Files
- particles: data/particles.csv
- samples: data/samples.csv
- index_samples: data/index_samples.csv
- index_particles: data/index_particles.csv
- splits: splits/splits.json
- taxonomy_snapshot: taxonomy_snapshot.yaml
- checksums: checksums.sha256

## Label Distribution
### samples.label (primary)
- C01_Uniform: 100
- C02_EdgeBiased: 100
- C03_Ring: 100
- C04_Sector_Edge: 100
- C05_Sector_Internal: 100
- C06_RadialLines: 100
- C07_StraightLine: 100
- C08_CurvedScratch: 100
- C09_Spiral: 100
- C10_Hotspot_Iso: 100

### samples.label_fine (or label)
- C01_Uniform: 100
- C02_EdgeBiased: 100
- C03_Ring: 100
- C04_Sector_Edge: 100
- C05_Sector_Internal: 100
- C06_RadialLines: 100
- C07_StraightLine: 100
- C08_CurvedScratch: 100
- C09_Spiral: 100
- C10_Hotspot_Iso: 100

## Splits
- ratios: test=0.100, train=0.800, val=0.100
- test: n_samples=100, n_particles=9868
- train: n_samples=800, n_particles=85589
- val: n_samples=100, n_particles=10553

## Schema
### particles
- sample_id: str (required)
- particle_id: int (required)
- r_norm: float (required)
- r_mm: float (required)
- theta_rad: float (required)
- size_um: float (required)
- label_fine: str (required)
- label: str (required)
- x_mm: float (optional)
- y_mm: float (optional)
- component_label_fine: str (optional)
- component: str (optional)
- component_id: int (optional)
- source: str (optional)

### samples
- sample_id: str (required)
- label: str (required)
- n_particles: int (required)
- pattern_params: str (required)
- seed_offset: int (required)
- label_coarse: str (optional)
- label_family: str (optional)
- labels_fine: str (optional)
- label_fine_primary: str (optional)
- components_json: str (optional)
