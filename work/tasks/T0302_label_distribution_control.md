# TASK: T0302 生成設定の高度化（ラベル比率/粒子数分布/パラメータ範囲をYAMLで制御）(P0)

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/09_EVALUATION_PROTOCOL.md
- docs/10_PROCESS_CATALOG.md

## Summary
生成データの内容を後から把握・調整しやすいように、**ラベル比率・粒子数分布・パターンパラメータ範囲**を Hydra YAML で体系的に管理できるようにする。

## Scope
- `process=generate` の入力設定を拡張し、以下を YAML で宣言できるようにする
  - ラベル比率（例: ring_narrow:0.2, hotspot_center:0.1 ...）
  - サンプルごとの粒子数分布（例: label別に Poisson/NegativeBinomial/固定値/範囲）
  - パターンパラメータの範囲（例: ring の r0 を [120, 145]mm からサンプル、sector角幅を [10,35]deg など）
- 出力 samples テーブルに `pattern_params`（JSON文字列など）を必ず入れ、後から追跡できるようにする（docs/04）
- QC（process=qc）で label 分布と粒子数分布が集計され、指定した比率に概ね一致することを確認できるようにする
  - “完全一致” ではなく許容誤差を設定（例: ±3%）

## Non-goals
- UI/GUI の作成
- 自動パラメータ探索（それはT0402で扱う）

## Acceptance Criteria
- [ ] Hydra YAML のみで label 比率・粒子数分布・主要パラメータ範囲を設定できる
- [ ] 生成後の `metrics/label_summary.csv`（または相当）で、指定比率に近い分布が得られる（許容誤差内）
- [ ] `samples` に `pattern_params` が入り、再現性のための情報が残る
- [ ] seed固定で再生成すると同一分布が得られる（docs/00）

## Verification
- `pytest -q -k T0302`

## Implementation Notes
- 既存の “label list / ratio” 指定がある場合は後方互換を保つ
- YAML の記述が増えても、registry + config group で秩序を維持する（docs/11）
