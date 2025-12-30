# 20_EXAMPLES — generate→qc→viz の最短手順

## 0. 前提
- 実行場所は repo root（`/Users/kawahito/Desktop/synthlab_scaffold`）
- `seed` は必須（docs/00）
- 例は Hydra 風 override の最小セット（docs/03）

## 1. 最短コマンド（CSV）
`pyarrow` が無い環境でも動く CSV 出力の例。

```bash
python -m synthlab.cli.main process=generate seed=123 run_name=demo_001 \
  wafer_particles.n_samples=200 \
  wafer_particles.io.format=csv

python -m synthlab.cli.main process=qc seed=123 run_name=demo_001 \
  wafer_particles.qc.input.run_name=demo_001

python -m synthlab.cli.main process=viz seed=123 run_name=demo_001 \
  wafer_particles.viz.input.run_name=demo_001
```

Parquet を使う場合は `wafer_particles.io.format=csv` を外し、`pyarrow` を入れる。

## 2. 出力の見方（runs/）
- `runs/<run_name>/wafer_particles.process.generate/`
  - `data/particles.*` `data/samples.*` `metrics/generate_summary.json`
- `runs/<run_name>/wafer_particles.process.qc/`
  - `metrics/qc.json` `metrics/label_summary.csv`
- `runs/<run_name>/wafer_particles.process.viz/`
  - `plots/scatter_label_*.png` `plots/histograms.png` `metrics/viz_summary.json`

## 3. Hydra override 例（よく使うもの）
### サンプル数・粒子数
- `wafer_particles.n_samples=500`
- `wafer_particles.n_particles=300`

### ラベル比率の調整（ratio mode）
比率は重み。0 を指定するとそのラベルは生成されない。

```bash
python -m synthlab.cli.main process=generate seed=7 run_name=ratio_demo \
  wafer_particles.n_samples=300 \
  wafer_particles.label_selection.ratios.ring_narrow=0.4 \
  wafer_particles.label_selection.ratios.ring_wide=0.4 \
  wafer_particles.label_selection.ratios.random_uniform=0.1 \
  wafer_particles.label_selection.ratios.random_edge_biased=0.1 \
  wafer_particles.io.format=csv
```

### QC / 可視化の調整
- `wafer_particles.qc.bins.r.count=40`
- `wafer_particles.viz.samples_per_label=2`
- `wafer_particles.viz.scatter.max_points=2000`

## 4. トラブルシュート（最小）
- `seed is required` が出る: `seed=...` を追加する
- `input run_dir not found` が出る: `wafer_particles.qc.input.run_name` / `wafer_particles.viz.input.run_name` を確認
- 同じ `run_name` が存在する場合: 出力が `run_name_1` などに自動で変わるので `runs/` を確認
- `pyarrow is required` が出る: `wafer_particles.io.format=csv` を使う
- `matplotlib is required` が出る: viz をスキップするか依存を入れる
