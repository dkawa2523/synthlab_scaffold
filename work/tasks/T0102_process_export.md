# TASK: T0102 process=export（P1）

## Contracts
- docs/10_PROCESS_CATALOG.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/09_EVALUATION_PROTOCOL.md

## Scope
- train/val/test split を作る（seed固定）
- dataset_id を確定（config_hash + schema_version等）
- 学習で扱いやすい index（sample単位/粒子単位）を整備

## Acceptance Criteria
- [ ] 下流学習で “読みやすい” パッケージになる（parquet + manifest + splits）
