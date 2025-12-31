# TASK: T0507 Export & dataset versioning upgrades (multi-label + labeling spec hash + dataset card) (P0)

## Why
- Addresses comparability and drift risks:
  - dataset_id must change when labeling layers/cause mappings change
  - export must support multi-label datasets for composed data

## Contracts
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/09_EVALUATION_PROTOCOL.md
- docs/10_PROCESS_CATALOG.md

## Scope
Upgrade `process=export` (or add `process=package_dataset`) to:
1) Support both single-label and multi-label:
   - If `samples` contains `labels_fine` (list), keep it.
   - Always keep `label_fine` if present (for backwards compatibility).
2) Integrate labeling spec (from T0501):
   - config: `export.labeling_spec_path` (optional)
   - config: `export.apply_labeling_spec` (default false)
   - If enabled:
     - apply derived label layers
     - store `labeling_spec_hash` in meta and dataset card
3) Dataset ID versioning:
   - dataset_id = hash of:
     - config_hash (resolved)
     - taxonomy_version
     - labeling_spec_hash (if applied)
     - metric_set_version (if applicable)
   - Store dataset_id in meta and dataset card.
4) Produce dataset card:
   - `reports/dataset_card.md` summarizing:
     - label distributions (fine + derived layers)
     - similarity groups counts (if spec includes them)
     - config snapshot hashes

## Acceptance Criteria
- [ ] dataset_id changes if and only if relevant inputs change (labeling spec content change must change dataset_id).
- [ ] Exported dataset is usable for ML training with multi-label and/or component columns.
- [ ] Dataset card exists and includes label distributions.

## Verification
- Add `tests/test_T0507_export_dataset_id_and_card.py`
  - Export twice with same config => same dataset_id
  - Export with modified labeling spec => different dataset_id
  - Assert dataset card exists
