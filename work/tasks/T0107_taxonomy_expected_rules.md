# TASK: T0107 タクソノミー拡張と期待特徴ルールの整備 (P1)

## Contracts
- docs/09_EVALUATION_PROTOCOL.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/00_INVARIANTS.md

## Summary
taxonomy_v1.yaml の “TODO” を解消し、ラベルごとの期待特徴（expected_rules）を具体化して QC 出力に反映させる。

## Scope
- `conf/wafer_particles/labels/taxonomy_v1.yaml` の expected_rules を具体化（TODO撤去）
- QC で taxonomy の expected_rules が出力に含まれることを保証する
- 今後の拡張に備え、記述を「カテゴリ→サブラベル→期待特徴」の形で読みやすく整える

## Acceptance Criteria
- [ ] `pytest -q tests/test_T0107_taxonomy_expected_rules.py` が通る
- [ ] taxonomy_v1.yaml 内の expected_rules から "TODO" が消える
- [ ] `process=qc` の出力（metrics）に expected_rules が含まれる（少なくとも1ラベルで確認）

## Implementation Notes
- ルール“判定”の厳密化はP2でも良いが、期待特徴の記述はP1で整備する

## Verification
- `pytest -q tests/test_T0107_taxonomy_expected_rules.py`
