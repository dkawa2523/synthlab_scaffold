# TASK: T0104 下流学習モデル実装（ベースライン分類器）(P0)

## Contracts
- docs/10_PROCESS_CATALOG.md
- docs/09_EVALUATION_PROTOCOL.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/11_PLUGIN_REGISTRY.md

## Summary
`process=train` / `process=eval` で動く **ベースライン分類器**を実装し、擬似データ（export出力）を学習データとして使える状態にする。

## Scope
- 依存追加（scikit-learn等）は避け、**NumPyのみで動く軽量モデル**を実装する
  - 例：Nearest Centroid / Prototype classifier（ラベルごとの特徴量平均ベクトルを学習し、最近傍で推論）
- `wafer_particles.model.*` の Plugin を追加し registry で解決できるようにする
- `process=train` が export artifact を入力として学習し、artifact契約に沿って出力する
- `process=eval` が train artifact（モデル）と export artifact（test）を入力として評価する
- `preds/` と `metrics/` を保存し、再現性を保証する（seedとresolved config）

## Non-goals
- 高度なモデル（PointNet等の深層学習）
- ハイパーパラメータ探索（P2）

## Acceptance Criteria
- [ ] `pytest -q tests/test_T0104_baseline_train_eval.py` が通る
- [ ] train artifact に `model/`（モデルファイル）と `metrics/train_summary.json` が出力される
- [ ] eval artifact に `preds/eval_predictions.(json|parquet|csv)` と `metrics/eval_summary.json` が出力される
- [ ] ランダム推測より高い精度が確認できる（生成データ上でOK）

## Implementation Notes
- 入力は `process=export` の artifact（splits + data）
- 特徴量はまず以下を最小セットとして実装（後で拡張可能に）
  - n_particles
  - rヒスト（固定bin; QCと同一binを推奨）
  - thetaヒスト（固定bin）
  - size統計（mean/std/quantiles）
- モデル保存は JSON+NPY など簡易形式で良い（互換性は後で整備）

## Verification
- `pytest -q tests/test_T0104_baseline_train_eval.py`
