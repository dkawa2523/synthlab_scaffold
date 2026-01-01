# TASK: T0705 粒径分布のQC/特徴量抽出（異常検出・学習用） (P1)

## Why
粒径分布を多様化すると、生成品質を担保するためのQCと、
将来の異常検出・特徴量学習に使える統計量が重要になります。

本タスクでは、生成済みデータから **粒径分布の特徴量**を抽出し、
レポート/メトリクスとして保存します。

## Contracts
- docs/10_PROCESS_CATALOG.md（Process追加/拡張ルール）
- docs/04_ARTIFACTS_AND_VERSIONING.md（metricsの保存場所）
- docs/00_INVARIANTS.md（再現性）

## Scope
1) `process=qc` もしくは新規 `process=size_qc` として以下を出力
- per-sample 統計:
  - mean, std, median
  - q05, q25, q75, q95
  - skewness, kurtosis（近似でOK: Fisher-Pearson）
  - tail_ratio（例: q95/q50, q99/q90 等）
- 集計:
  - size_model別のサンプル数/比率
  - size_model別の統計分布（平均・分散など）

2) 可能なら「理論分布 vs 実測粒径」のKS統計を計算（SciPy無し）
- gaussian/lognormal/weibull/pareto/mixture（mixtureは理論CDFが複雑なので非必須）
- gaussian CDFは erf で近似
- lognormal: log変換してgaussian CDF
- weibull, pareto: closed-form CDF

3) 出力物
- `reports/size_stats.csv`（per-sample）
- `reports/size_model_mix.json`（集計）
- （既存のmetrics契約があればその形式に従う）

## Non-goals
- 最高精度の統計推定（目的はQCとベンチマーク補助）
- 分布パラメータの推定（fit）（将来タスク）

## Acceptance Criteria
- [ ] 上記の per-sample 統計が作成でき、runs配下に保存される
- [ ] size_model 別の集計が保存される
- [ ] seed固定で同一入力なら同一出力になる

## Implementation Notes
- 大規模データでも動くように pandas groupby を中心に実装
- 出力の列名・JSONキーは docs/04_ARTIFACTS_AND_VERSIONING.md のルールに合わせる

## Verification
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=4
python -m synthlab.cli.main process=qc input_dir=runs/.../generate  # 既存のqcがある場合
# または
python -m synthlab.cli.main process=size_qc input_dir=runs/.../generate
```
