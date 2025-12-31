# TASK: T0401 実測少数データからのパターンパラメータ推定（キャリブレーションの入口）(P1)

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/09_EVALUATION_PROTOCOL.md
- docs/10_PROCESS_CATALOG.md
- docs/11_PLUGIN_REGISTRY.md
- docs/05_SECURITY_SECRETS.md

## Summary
実測（少数、十数枚）から、パターン生成器の主要パラメータ（例：リング半径/幅、セクタ角度中心/幅、エッジ偏り、ホットスポット位置/分散）を推定し、後続の距離最小化（T0402）につなげる。

## Scope
- 新規 Process（例）：`process=fit_params` または `process=calibrate_fit`
  - input: 実測 or “real扱い” の particles/samples（CSV/Parquet）
  - output: `metrics/estimated_params.json`（pattern別/label別）
- 推定器を plugin として登録（例: `wafer_particles.param_estimator.*`）
  - ring: rの平均/分散、theta coverage
  - sector: thetaの中心角・幅、rのエッジ近傍度
  - hotspot: 密度中心 (x,y) / (r,theta) と分散
  - radial/scratch: 主方向（角度）や本数の推定（簡易でOK）
- 実測がラベルを持たない場合でも動くよう、推定は “全体1クラス” でもよい（ラベルがあればラベル別に推定）

## Non-goals
- 完全に物理モデルに一致させる（P2以降）
- 高度な最尤推定（まずは頑健なヒューリスティックで良い）

## Acceptance Criteria
- [ ] `process=fit_params` が実行でき、estimated_params.json が artifact に保存される
- [ ] 疑似“実測”データ（合成から抜粋して作る）に対し、概ね元のパラメータ近傍を推定できる（誤差許容を設定）
- [ ] 推定に使った指標（r統計、theta統計等）が同時に保存され、説明可能性がある

## Verification
- `pytest -q -k T0401`

## Implementation Notes
- テストでは “realデータ” を外部に依存させないため、既存 generator で作ったデータを `fit_params` 入力に使い、推定が元パラメータを回収できることを確認する
- そのため `fit_params` は Parquet/CSV のどちらでも読めるI/Oにする
