# TASK: T0701 追加粒径分布モデル（lognormal / weibull / pareto）実装 (P0)

## Why
半導体製造で観測されるパーティクル粒径分布は、ガウス分布だけでは表現できないケースが多いです。

- **対数正規分布**: 乗法要因・成長/凝集の結果として現れやすく、粒径分布の定番。
- **ワイブル分布**: 粒子の破砕や粒度分布（Rosin–Rammler）として経験的に有用。
- **パレート分布（power-law）**: 重尾（ヘビーテール）を持ち、異常混入や最悪ケースのシミュレーションに有用。

本タスクでは、既存の `wafer_particles.size_models` に **新しい分布関数**を追加し、
Hydra/YAML から選択・パラメータ指定できるようにします。

## Contracts
- docs/00_INVARIANTS.md（seed固定で完全再現）
- docs/03_CONFIG_CONVENTIONS.md（Hydra/YAML）
- docs/11_PLUGIN_REGISTRY.md（追加しやすい拡張点）
- docs/04_ARTIFACTS_AND_VERSIONING.md（生成条件が追跡可能）

## Scope
1) 既存サイズモデル実装に以下を追加
   - `type: lognormal`
   - `type: weibull`
   - `type: pareto`

2) 各モデルのパラメータ（例）
   - lognormal:
     - `mu_log`（log-domain mean）
     - `sigma_log`（log-domain std, >0）
   - weibull:
     - `k`（shape, >0）
     - `lambda_um`（scale in µm, >0）
   - pareto:
     - `alpha`（shape, >0）
     - `xm_um`（minimum in µm, >0）  
       生成は `x = xm_um * (1 + rng.pareto(alpha))` を基本とする（numpyのparetoは0以上のPareto-II）。

3) 既存と同様に **clamp**
   - `min_um` / `max_um` を共通に適用（常に [min_um, max_um] に収める）

4) 既存の `param_space`（T0502）を再利用し、パラメータに **ParamSpec** を許可
   - 例: `mu_log: {dist: uniform, low: -5.0, high: -1.0}` 等
   - ParamSpecは run全体固定 or per-sample の両方で利用できるようにする

## Non-goals
- SciPy依存の導入（numpy + 標準ライブラリで完結）
- すべての分布の厳密なフィッティング（将来タスク）

## Acceptance Criteria
- [ ] `wafer_particles.size_models.type` に `lognormal|weibull|pareto` を指定できる
- [ ] 各パラメータが float と ParamSpec の両方を受け付ける
- [ ] 生成された粒子サイズが常に [min_um, max_um] に収まる
- [ ] seed固定で完全再現（同一設定→同一出力）
- [ ] Doctorで不正パラメータ（sigma<=0 等）を検知してFAILできる（詳細はT0708）

## Implementation Notes
- 既存のサイズモデル実装（SizeModelクラス/関数）を踏襲し、**新規モデルをプラグインとして追加**する形にする
- RNGは numpy Generator を使用し、global random stateは使わない
- 可能なら `size_models` を「モデル名→実装」の辞書/registryに寄せ、今後の追加を容易にする

## Verification
最低限、以下のスモークが通ること（本格テストはT0708）。
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=1
```
