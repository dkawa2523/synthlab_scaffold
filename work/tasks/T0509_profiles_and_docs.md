# TASK: T0509 Profiles for parameter ranges + operational docs update (P1)

## Why
- Addresses realism gap and parameter-range management:
  - Different tools/processes require different parameter distributions.
  - Avoids editing many pattern YAMLs by switching a profile.

## Contracts
- docs/03_CONFIG_CONVENTIONS.md
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## Scope
1) Profile system:
- Add Hydra group `wafer_particles/profiles` with at least:
  - `default.yaml` (already included by patch)
  - `etch_rie_example.yaml` (already included by patch; placeholder)
- Implement deep-merge override:
  - profile overrides pattern param ranges, size_model clamp, particle counts, etc.
  - record active profile name + profile hash in meta.

2) Docs update:
- Add a new doc: `docs/14_LABELING_AND_GROUPS.md`
  - phenotype vs derived layers vs cause hypotheses
  - how to use external labeling spec file
  - recommended similarity groupings for current labels (reference)
- Update `docs/10_PROCESS_CATALOG.md`:
  - add `process=labeling_apply`, `process=compose`, `process=pattern_coverage`

## Acceptance Criteria
- [ ] User can switch a profile in Hydra and see parameter distributions change.
- [ ] Active profile is recorded in artifacts.
- [ ] Docs exist and explain the new labeling/grouping mechanism and similarity groups.

## Verification
- Add `tests/test_T0509_profile_override_effect.py`
  - Run a small generation with default vs profile override and assert a measurable difference (e.g., n_particles mean).
- Doc verification can be minimal:
  - assert files exist and contain required headings.
