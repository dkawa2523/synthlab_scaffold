# TASK: T0204 実測比較の距離指標拡張（Distribution/Spatial distance report）(P0)

## Summary
- synthetic と real（または2つのrun）の差を、ヒストグラム/粒径/空間統計の距離として定量化する。
- “見た目” だけでなく、**粒子テーブルとして比較**できるレポートを metrics/plots に残す。

## Contracts (MUST READ)
- docs/09_EVALUATION_PROTOCOL.md（比較ルール）
- docs/04_ARTIFACTS_AND_VERSIONING.md（artifact出力）
- docs/05_SECURITY_SECRETS.md（実測データ扱い）
- docs/00_INVARIANTS.md（skew禁止）

## Scope
- `process=compare`（または既存 compare の拡張）を実装/拡張し、2つの入力を比較できるようにする
  - 入力A: `compare.a_run`（synthetic run）
  - 入力B: `compare.b_run`（real run または別synthetic run）
- 距離指標（最低限）
  - rヒスト: JS divergence / KL（smoothingあり）
  - thetaヒスト: JS divergence
  - size分布: KS統計 + Wasserstein距離
  - 2D密度: polar grid を作り L1/L2 差（簡易でOK）
  - 空間統計: 最近傍距離分布のKS（簡易）
- 出力
  - `metrics/compare_summary.json`（機械可読）
  - `metrics/compare_table.csv`（人間が見やすい）
  - `plots/compare_*.png`（ヒスト重ね描き等。任意だが推奨）
- “同一データ比較で距離 ~0” を確認できる自己一致モード（同じrunを入れたとき）

## Non-goals
- 統計検定の厳密なp値
- 物理シミュレータとの一致

## Inputs / Outputs
- Inputs:
  - generate/export で作られた run artifact（particles/samples）
- Outputs:
  - compare artifact（config/meta/metrics/plots）

## Acceptance Criteria (MUST)
- [ ] `process=compare` が A/B の run を指定して実行できる
- [ ] compare_summary.json に距離指標が全て入る
- [ ] 同一run同士の比較で距離が小さい（少なくとも0ではないが極小になる設計）
- [ ] 実測パスなど機密がログに平文で出ない（必要なら basename のみ）

## Verification (MUST)
1) データA生成
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=30 seed=10
```

2) データB生成（seedやパターンを変える）
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=30 wafer_particles/patterns=ring_wide seed=11
```

3) compare（A vs B）
```bash
python -m synthlab.cli.main process=compare compare.a_run="runs/<runA>/generate" compare.b_run="runs/<runB>/generate" seed=12
```

4) compare（A vs A：自己一致）
```bash
python -m synthlab.cli.main process=compare compare.a_run="runs/<runA>/generate" compare.b_run="runs/<runA>/generate" seed=13
```

5) 生成物チェック（簡易）
```bash
python - << 'PY'
import json, glob
p = sorted(glob.glob("runs/*/compare/metrics/compare_summary.json"))[-1]
d = json.load(open(p))
assert "r_hist_js" in d
assert "theta_hist_js" in d
assert "size_ks" in d
assert "size_wasserstein" in d
print("OK:", p)
PY
```

6) pytest
```bash
pytest -q
```

## Dependencies
- depends_on: [T0102]  # exportがあると比較の入力が統一できる（generateのみでも可だがここでは依存）

## Implementation Notes
- bin定義は compare config に固定し、比較可能性を担保（docs/09）
- JS/KL のゼロ割回避に smoothing（epsilon）を入れる
- 2D密度は `r_bin x theta_bin` のグリッドでOK（高速）
- 空間統計は近傍距離のサンプル数が多いと重いので、必要ならサブサンプルする（seedで固定）

## DoD
- [ ] metrics/json+csv が出る
- [ ] 最低限の plots（任意だが推奨）
- [ ] tests（自己一致が小さいことのテスト）
