# next_tasks_T0701-T0708（粒径分布 拡張パック）

このパックは **dkawa2523/synthlab_scaffold** リポジトリに対して、
粒子サイズ分布（粒径分布）の拡張を Codex/autodev で実装するためのタスク群です。

## 目的（このパックで実現すること）
- 粒径分布モデルを追加（lognormal / weibull / pareto）
- 生成データセット内で複数の粒径分布を混在（サンプルごとに分布タイプを選択）
- 分布固有パラメータの範囲を Hydra/YAML で指定し、per-sampleに揺らぐ生成が可能
- 生成後に size_model / size_params を追跡できる（samplesに保存）
- 将来の異常検出・学習拡張向けに、統計/QCや異常ラベル付与の拡張（P1）

---

## 使い方（既存repoに追加）

### 1) repo 直下で unzip
```bash
cd /path/to/dkawa2523/synthlab_scaffold
unzip /path/to/next_tasks_T0701-T0708.zip -d .
```

### 2) queue にタスク追加
```bash
python patch/apply_queue_patch.py patch/queue_patch_T0701_T0708.json
```

### 3) autodev を回す（Codexで自動実装）
```bash
python autodev/run_loop.py --loop
```

---

## 実行スモーク（タスク完了後）
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=1
```

---

## 注意
- T0703/T0705/T0706 は P1（任意）です。P0を先に固めたい場合は queue.json で priority を調整してください。
- 既存の `size_models.type: gaussian` の単一指定は後方互換として残します（壊さない）。
