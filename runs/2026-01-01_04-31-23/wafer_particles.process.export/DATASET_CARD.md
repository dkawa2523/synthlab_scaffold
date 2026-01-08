# Dataset Card

## Overview
- dataset_id: wafer_particles.v1_taxonomy_v2_2381a1391f5a
- domain: wafer_particles
- schema_version: wafer_particles.v1
- taxonomy_version: taxonomy_v2
- created_at: 2026-01-01T04:31:23.415992+00:00

## Config
- config_hash: e2fa441be014
- dataset_config_hash: c7e14cee1ffe
- input_config_hash: 6741636546cd

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
- C01_Uniform: 91
- C02_EdgeBiased: 91
- C03_Ring: 91
- C04_Sector_Edge: 91
- C05_Sector_Internal: 91
- C06_RadialLines: 91
- C07_StraightLine: 91
- C08_CurvedScratch: 91
- C09_Spiral: 91
- C11_Hotspot_Elliptic: 91
- edge_sector_left: 9
- edge_sector_right: 9
- hotspot_center: 5
- radial_lines: 9
- random_edge_biased: 2
- random_uniform: 2
- ring_narrow: 18
- ring_wide: 18
- scratch_horizontal: 9
- scratch_vertical: 9

### samples.label_fine (or label)
- C01_Uniform: 91
- C02_EdgeBiased: 91
- C03_Ring: 91
- C04_Sector_Edge: 91
- C05_Sector_Internal: 91
- C06_RadialLines: 91
- C07_StraightLine: 91
- C08_CurvedScratch: 91
- C09_Spiral: 91
- C11_Hotspot_Elliptic: 91
- edge_sector_left: 9
- edge_sector_right: 9
- hotspot_center: 5
- radial_lines: 9
- random_edge_biased: 2
- random_uniform: 2
- ring_narrow: 18
- ring_wide: 18
- scratch_horizontal: 9
- scratch_vertical: 9

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
- size_model: str (optional)
- size_params_json: str (optional)
- is_size_anomaly: int (optional)
- size_anomaly_type: str (optional)
- label_coarse: str (optional)
- label_family: str (optional)
- labels_fine: str (optional)
- label_fine_primary: str (optional)
- components_json: str (optional)
