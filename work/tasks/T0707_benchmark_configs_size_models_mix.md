# TASK: T0707 ベンチマーク設定（複数粒径分布mix）追加 (P0)

## Why
新しい size model 機能（T0701–T0704）を、ユーザがすぐ使えるように
**ベンチマーク用Hydra config**を提供します。

（異常ラベル付きベンチマークは T0706 で別途追加します）

## Contracts
- docs/03_CONFIG_CONVENTIONS.md（Hydra）
- docs/04_ARTIFACTS_AND_VERSIONING.md（出力の比較可能性）
- docs/00_INVARIANTS.md（seed）

## Scope
以下の config を追加（conf/benchmarks/wafer_particles/）

1) `benchmark_macro10_300mm_1k_generate_size_models_mix.yaml`
- 300mm / 1000 samples / label macro10
- size_models: selection ratio で gaussian/lognormal/weibull/pareto を混在
- n_particles: 10–200
- size clamp: 10–1000nm

2) `benchmark_macro10_300mm_20_generate_size_models_mix_smoke.yaml`
- 軽量のsmoke用（20 samples）

3) （任意）exportのsmoke config
- `benchmark_macro10_300mm_20_export_size_models_mix_smoke.yaml`
- 生成→export のパイプラインが通ることを確認

## Acceptance Criteria
- [ ] 上記configが追加され、READMEの実行例が成立する
- [ ] smoke config が短時間で完走する

## Verification
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=1
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_1k_generate_size_models_mix seed=42
```
