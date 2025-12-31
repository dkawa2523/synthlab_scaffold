# TASK: T0501 Labeling layers & cause hypotheses (external file) + post-generation relabel process (P0)

## Why
- Addresses the operational risk: **label granularity becomes unmanageable** and “pattern label == root cause” is falsely assumed.
- Separates:
  - **phenotype labels** (fine labels = generator pattern_id)
  - **user-defined derived hierarchies** (family/location/geometry/any custom layer)
  - **cause hypotheses** (metadata, NOT ground-truth)
- Enables post-generation mapping via an **external YAML file** (can live outside repo).

## Contracts
- docs/00_INVARIANTS.md (config truth, comparability, skew禁止)
- docs/03_CONFIG_CONVENTIONS.md (Hydra group/override)
- docs/04_ARTIFACTS_AND_VERSIONING.md (artifact contract, meta/config hash)
- docs/10_PROCESS_CATALOG.md (Process I/O)
- docs/11_PLUGIN_REGISTRY.md (extension rules)

## Scope
1) Define an external labeling spec format (YAML) and ship a default example:
   - File: `conf/wafer_particles/labeling/label_layers_example_v1.yaml` (already included by this patch)
   - Must support:
     - `layers: {layer_name: {fine_label: derived_value}}` (any number of layers)
     - `similarity_groups: [{name, description, members:[fine_label,...]}]` (for reporting)
     - `cause_hypotheses: {cause_id: {title, description, confidence, related_labels:[...]}}` (metadata)

2) Implement a labeling module:
   - `LabelingSpec.load(path)`, `LabelingSpec.hash()` (stable SHA256 of canonicalized content)
   - `apply_to_particles(df_particles)`:
     - Map `label_fine` to derived columns for each layer (e.g. `label_family`, `label_location`, ...).
     - Unknown labels -> "UNKNOWN"
   - `apply_to_samples(df_samples)`:
     - If samples have `label_fine` (single-label), derive `label_<layer>`.
     - If samples have `labels_fine` (multi-label list), derive:
       - `labels_<layer>` (unique list)
       - and optionally `label_<layer>_primary` from `label_fine_primary` if present.

3) Add a new Process: `process=labeling_apply`
   - Input: an exported dataset run directory (particles + samples + manifest)
   - Input: `labeling.spec_path` (user can override to any external YAML)
   - Output: a new run dir artifact containing:
     - updated `particles.parquet` + `samples.parquet` (added columns)
     - `meta/labeling_spec.yaml` snapshot
     - `meta/labeling_spec_hash.txt`
     - `reports/labeling_layers_summary.json` (counts per derived label)
     - `reports/similarity_groups_summary.json`

4) Export integration (minimal):
   - Add optional flag to `process=export`:
     - `export.apply_labeling_spec=true/false` (default false)
     - If true, apply labeling spec before writing artifacts, and include spec hash in meta.

## Non-goals
- Automatic root-cause inference. Cause hypotheses are metadata only.
- UI building (report JSON/MD is enough).

## Acceptance Criteria
- [ ] User can run `process=labeling_apply` with an external YAML path and get a new dataset artifact with derived label columns.
- [ ] Multiple label layers are supported without code changes (add new `layers.<name>` in YAML => new columns appear).
- [ ] Unknown fine labels are handled deterministically as `"UNKNOWN"`.
- [ ] Spec hash is stable and written into artifact meta.
- [ ] Similarity groups and cause hypotheses are exported into report artifacts (not necessarily used for training).
- [ ] No changes violate docs/00 invariants (run-to-run comparability).

## Implementation Notes
- Use OmegaConf/Hydra-friendly YAML loading (avoid extra dependencies).
- Keep column naming deterministic:
  - For layer name `family` => `label_family` and `labels_family`.
  - Sanitize layer names into safe snake_case.
- Parquet list columns are allowed for `labels_*`. If list type is problematic, store JSON strings consistently (but choose one and document).
- Do NOT treat cause_hypotheses as training labels by default.

## Verification
- Add `tests/test_T0501_labeling_apply.py`
  - Generate a tiny synthetic dataset (or reuse existing test fixtures).
  - Run labeling apply in-process (call function or CLI).
  - Assert:
    - new columns exist for at least `family/location/geometry`
    - unknown mapping yields "UNKNOWN"
    - spec hash file exists and is stable
