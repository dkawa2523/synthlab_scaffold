# TASK: T0502 Param-space sampling + strict config validation + doctor gate (P0)

## Why
- Addresses high-risk operational failures:
  - config肥大化 → 設定ミス → 比較不能/再現不能
  - パラメータ範囲の誤設定 → 非現実データの大量生成
- Provides a single, reusable engine to sample continuous parameters from YAML specs.

## Contracts
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/10_PROCESS_CATALOG.md

## Scope
1) Implement `param_space` utilities (Hydra/YAML-driven):
   - Support fixed values (number/string/bool) and distribution specs:
     - `{dist: uniform, low, high}`
     - `{dist: loguniform, low, high}`
     - `{dist: normal, mean, std, min?, max?}`
     - `{dist: truncnorm, mean, std, min, max}`
     - `{dist: beta, alpha, beta, min?, max?}` (map to [min,max])
     - `{dist: gamma, k, theta}` or `{dist: gamma, shape, scale}`
     - `{dist: vonmises, mu, kappa}` (for angles)
     - `{dist: choice, values:[...], weights:[...]}` (categorical)
   - A canonical validator:
     - unknown `dist` => error
     - low>=high => error
     - missing required keys => error
   - Deterministic sampling with injected RNG (seed handling consistent with docs/00).

2) Integrate strict validation into `process=doctor`:
   - Validate all enabled pattern configs:
     - param specs valid
     - n_particles spec valid (min<=max, etc.)
     - wafer radius >0
     - optional patterns (O01/O02) remain disabled by default (warn if enabled without explicit override)
   - Validate size_model specs:
     - clamp ranges valid
     - distribution parameters valid

3) Add a small `schema_version` field for pattern configs and labeling specs:
   - doctor warns if version mismatch.

## Acceptance Criteria
- [ ] A single sampling API exists and is used across pattern implementations (no ad-hoc random sampling scattered).
- [ ] `process=doctor` fails fast on invalid param specs or inconsistent ranges.
- [ ] doctor emits actionable error messages (which key, which file/group).
- [ ] Reproducible sampling given fixed seed.

## Implementation Notes
- Use numpy RNG; do not rely on global random state.
- Prefer normalized coordinates in configs (0..1) for wafer scaling (doctor can validate 0..1 ranges).

## Verification
- Add `tests/test_T0502_param_space_validation.py`
  - valid specs sample without error
  - invalid specs raise (unknown dist, low>=high, missing keys)
- Add `tests/test_T0502_doctor_catches_invalid_config.py`
  - create a minimal invalid override config and assert doctor fails
