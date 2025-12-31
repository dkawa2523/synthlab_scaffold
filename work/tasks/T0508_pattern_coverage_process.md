# TASK: T0508 Process=pattern_coverage (new pattern needed?) + composite search report (P0)

## Why
- Required by spec: evaluate whether new pattern registration is needed from real deposition data.
- Addresses operational risk: “new pattern” vs “param range insufficient” vs “composite recipe enough”.

## Contracts
- docs/00_INVARIANTS.md
- docs/09_EVALUATION_PROTOCOL.md
- docs/10_PROCESS_CATALOG.md

## Scope
Add `process=pattern_coverage`:
- Input:
  - `coverage.real_input` (CSV/Parquet OR existing run dir)
  - `coverage.pattern_set` (enabled patterns)
  - `coverage.search_budget` (n_samples per pattern)
  - `coverage.allow_composite_search` (true/false)
  - `coverage.composite_k` (2 or 3)
  - `coverage.threshold_new_pattern` (float)
- Steps:
  1) Compute real metrics (reuse QC/compare metrics if available).
  2) For each pattern:
     - sample candidate params from YAML distributions (budget)
     - generate synthetic candidates
     - compute distance to real
     - keep best-k
  3) If composite search enabled:
     - try combining top candidates of different patterns (2-3 components) and re-evaluate distance.
  4) Produce report:
     - `reports/coverage_summary.json` (top patterns, distances, suggested action)
     - `reports/coverage_summary.md`
     - optional plots: real vs best-fit density, residual map
- Output:
  - Best-fit pattern_id(s), best params, distance breakdown.
  - Decision:
    - “Existing pattern fits”
    - “Composite recipe recommended”
    - “New pattern likely needed” (distance > threshold even after composite)

## Acceptance Criteria
- [ ] Running coverage produces a deterministic report artifact.
- [ ] Coverage can identify the correct generating pattern on synthetic proxy-real tests (top-3).
- [ ] Composite search can improve distance when proxy-real is composite.

## Implementation Notes
- To avoid huge compute, make budgets small by default but configurable.
- The “decision” must be explainable (distance components + residual plot).

## Verification
- Add `tests/test_T0508_pattern_coverage_proxy_real.py`
  - Create proxy-real by generating a known pattern sample
  - Run coverage and assert the known pattern appears in top-3
