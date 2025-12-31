# TASK: T0108 実測データ比較パイプラインの実装 (P1)

## Contracts
- docs/09_EVALUATION_PROTOCOL.md
- docs/05_SECURITY_SECRETS.md
- docs/10_PROCESS_CATALOG.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## Summary
実測データ（粒子テーブル）を取り込み、synthetic の QC 指標と **同一指標で比較**できる Process を追加する。

## Scope
- 新 Process：`process=compare_real`（名称は既存規約に合わせて良い）
  - 入力A: real particles table（CSV/Parquet） + 任意のsamplesメタ（なければ自動生成）
  - 入力B: synthetic run（generate/export/qc artifact）
  - 出力: real の metrics、synthetic vs real の距離（差異）を metrics に保存
- セキュリティ：入力パスは config/env で与え、実測データを repo に同梱しない

## Acceptance Criteria
- [ ] `pytest -q tests/test_T0108_compare_real_pipeline.py` が通る
- [ ] compare_real を実行すると、artifact に `metrics/real_metrics.json` と `metrics/synth_vs_real_diff.json`（または同等）が保存される
- [ ] “同じデータをrealとして入力”した場合、差分が小さい（テストで確認）

## Implementation Notes
- 実測ファイルが無い環境でもテストできるように、テストでは synthetic の一部を real として入力する
- 距離は簡易でOK（例：ヒストグラムのL1/L2、KS、平均差など）。まずは “比較できる” を優先

## Verification
- `pytest -q tests/test_T0108_compare_real_pipeline.py`
