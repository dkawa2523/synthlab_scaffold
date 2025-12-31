# TASK: T0203 点過程ジェネレータ追加（Inhom Poisson / Cluster / Repulsive）(P1)

## Summary
- 物理的に起こりやすい “ランダムだが構造を持つ” 付着を表現するため、点過程ベースの generator を追加する。
- 既存のパターン（ring/sector/scratch等）とは別系統として registry に追加し、Hydra group で選択可能にする。

## Contracts (MUST READ)
- docs/00_INVARIANTS.md（再現性）
- docs/11_PLUGIN_REGISTRY.md（pluginとして追加）
- docs/09_EVALUATION_PROTOCOL.md（QC指標と対応）
- docs/03_CONFIG_CONVENTIONS.md（Hydra group）

## Scope
- 以下の generator plugin を追加（名前は案、最終は一貫性を優先）
  - `wafer_particles.pattern.pp_inhom_poisson`：
    - 強度 λ(r,θ) をパラメータ化（例：edge bias、角度偏り、勾配）
  - `wafer_particles.pattern.pp_thomas_cluster`（Neyman-Scott/Thomas）：
    - 親点→子点でクラスタ生成（ホットスポットを確率的に多数生成）
  - `wafer_particles.pattern.pp_strauss_repulsive`（簡易）：
    - 近接点を抑制する反発（最短距離制約 or 近傍受理確率）
- 既存の size_model をそのまま適用できること（位置生成と粒径割当を分離）
- QC を最小限拡張（必要なら）
  - 最近傍距離の要約（mean/quantile）を metrics に追加し、cluster/repulsive の差が見えるようにする

## Non-goals
- 厳密な統計推定（モデルフィット）
- LGCP 等の重いモデル（P2以降）

## Inputs / Outputs
- Outputs:
  - 新pattern plugin 実装 + config group追加
  - tests（再現性、簡易統計差）

## Acceptance Criteria (MUST)
- [ ] 3種類の点過程パターンを Hydra で選択して generate できる
- [ ] 同一seedで同一出力
- [ ] QCで最近傍距離などの統計が出力され、cluster と repulsive で傾向差が見える（完全に分離しなくてもよい）

## Verification (MUST)
1) inhom poisson
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=3 wafer_particles/patterns=pp_inhom_poisson seed=3
python -m synthlab.cli.main process=qc input_run="runs/<run_name>/generate" seed=3
```

2) thomas cluster
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=3 wafer_particles/patterns=pp_thomas_cluster seed=4
python -m synthlab.cli.main process=qc input_run="runs/<run_name>/generate" seed=4
```

3) repulsive
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=3 wafer_particles/patterns=pp_strauss_repulsive seed=5
python -m synthlab.cli.main process=qc input_run="runs/<run_name>/generate" seed=5
```

4) pytest
```bash
pytest -q
```

## Dependencies
- depends_on: [T0201]  # taxonomy整合（coarse/family付与が必要なら）

## Implementation Notes
- wafer境界（半径300/2=150mm）内に必ず収める（reject sampling）
- theta は 0..2π に正規化
- Strauss は “厳密” でなくてよい。P1では最短距離制約（blue-noise風）でも可。
- 生成速度が落ちやすいので、n_particles が多いときに破綻しないよう上限/早期停止の安全策を入れる

## DoD
- [ ] 3パターン + config + tests
- [ ] QCの追加メトリクス（必要なら）
