# TASK: T0006 粒径モデル（lognormal/gaussian/mixture）とラベル別割当

## Contracts
- docs/11_PLUGIN_REGISTRY.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## Scope
- size_model を plugin として実装
  - gaussian
  - lognormal
  - mixture（混合比+成分）
- ラベル別に size_model を切替できる config
- 生成粒径の統計（平均/分位など）を qc で扱えるよう準備

## Acceptance Criteria
- [ ] particles に size_um が必ず入る
- [ ] ラベル別設定が可能
- [ ] 乱数が seed で再現できる

## Verification
- 同一seedの2回生成で size 分布が一致
