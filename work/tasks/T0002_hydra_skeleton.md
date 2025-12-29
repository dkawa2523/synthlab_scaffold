# TASK: T0002 Hydra設定（conf/）の規約に沿ったスケルトン作成

## Contracts
- docs/03_CONFIG_CONVENTIONS.md
- docs/00_INVARIANTS.md

## Scope
- conf/ を作成し、root `conf/config.yaml` と group を用意
- domain=wafer_particles, process=doctor/generate/qc/viz の雛形YAML作成
- taxonomy（labels/taxonomy_v1.yaml）の雛形を置く

## Acceptance Criteria
- [ ] Hydra が解決できる defaults 構成になっている
- [ ] run dir 規約（runs/<run_name>/<process>）が設定されている
- [ ] seed が必須として扱える（未指定はエラー or doctorで警告）

## Verification
- `python -m synthlab.cli.main process=doctor seed=1`
- config/resolved.yaml が group を含めて保存される

## DoD
- [ ] conf/ 構造が docs/03 に沿う
