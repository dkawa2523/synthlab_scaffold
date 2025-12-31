# TASK: T0506 Process=compose (random overlay) with multi-label + component tracing (P0)

## Why
- Addresses the high-risk issue: composite mixtures make single-label training invalid.
- Enables realistic multi-cause scenarios while preserving interpretability.

## Contracts
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/10_PROCESS_CATALOG.md

## Scope
Add a new Process `process=compose`:
- Input:
  - `compose.input_run_dir` (exported dataset or generate output)
  - `compose.n_samples_out`
  - `compose.n_components` (fixed or distribution spec)
  - `compose.component_sampling` (weights by fine label, allow duplicates yes/no)
  - `compose.particle_budget` (how to allocate particle counts per component)
- Output:
  - New dataset with:
    - particle-level: `component_id`, `component_label_fine`
    - sample-level: `labels_fine` (list), `label_fine_primary` (optional)
    - optionally derived label layers if `export.apply_labeling_spec` is on later
- Deterministic by seed.

## Acceptance Criteria
- [ ] Compose produces correct number of output samples and retains all particles.
- [ ] Component tracing exists at particle-level and supports audit/visualization.
- [ ] Sample-level multi-label list exists and is consistent with components.
- [ ] Process follows artifact contract (config/meta/metrics/preds/plots as applicable).

## Implementation Notes
- Compose should NOT require re-running generators. It should reuse already-generated samples and merge them.
- Implement a clear collision policy for sample_id (new ids).
- Keep a `compose_manifest.json` describing which source samples were used.

## Verification
- Add `tests/test_T0506_process_compose_multilabel.py`
  - Create tiny input dataset (2 labels) and compose
  - Assert:
    - component columns exist
    - labels_fine contains expected set
    - reproducible with same seed
