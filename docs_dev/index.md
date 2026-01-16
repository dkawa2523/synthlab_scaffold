# SynthLab Scaffold

**Wafer上のパーティクル付着パターン（点群：極座標 + 粒径）**を、ルールベースのパターン分布と複数の粒径分布で疑似生成するフレームワークです。

- 生成データは **CSV/Parquet** として出力し、分類/異常検出/特徴増強に利用できます。
- **Hydra** による設定管理で再現性を担保します（設定YAMLが真実）。
- パターン（C/K/O）や粒径分布（gaussian/lognormal/weibull/pareto/mixture 等）は **プラグイン的に拡張**できます。
- `doctor`（設定検証）・`qc`（統計/特徴量）・`pattern_coverage`（偏り確認）により、「生成→品質→配布」を同一の契約で回せます。

---

## 1. できること（クイックリファレンス）

| やりたいこと | 使うプロセス | 入力 | 出力 | 関連ドキュメント |
|---|---|---|---|---|
| 実行前に設定ミスを止める | `doctor` | config | PASS/FAIL + メッセージ | config_conventions.md / testing.md |
| 疑似データを生成する | `generate` | config | `particles`, `samples`, `meta` | process_catalog.md / patterns.md / size_models.md |
| 生成後の品質・統計を出す | `qc` | generate run | 統計CSV/JSON | process_catalog.md / testing.md |
| 可視化（散布図など） | `viz` | generate run | PNG等 | process_catalog.md |
| パターン偏り/欠落を調べる | `pattern_coverage` | run | coverageレポート | process_catalog.md |
| ラベル階層を後付けする | `labeling_apply` | dataset + spec | 派生ラベル列付きdataset | labeling.md |
| 複数パターンを重ね合わせる | `compose` | 既存run | 合成dataset | process_catalog.md |
| ML用にCSV/Parquetで配布する | `export` | dataset | `data/`, `splits/` | artifacts.md / process_catalog.md |

---

## 2. 前提（環境）

| 項目 | 推奨 | 補足 |
|---|---|---|
| Python | 3.10+ | リポジトリの `pyproject.toml` / `requirements.txt` に従う |
| 仮想環境 | venv/conda | どちらでも可 |
| 依存パッケージ | `pip install -r requirements.txt` | Parquet出力には `pyarrow` があると便利 |

---

## 3. クイックスタート（生成 → QC → Export）

### 3.1 設定プリセットを選ぶ
`conf/benchmarks/wafer_particles/` 配下のベンチマーク設定（YAML）を使うのが最も確実です。

例（名称はリポジトリで確認）:

| 目的 | 例: config-name | 説明 |
|---|---|---|
| macro10 + sizeモデル混在 + パラメータスイープ | `benchmark_macro10_300mm_1k_generate_size_models_mix_param_sweep_v1` | 10パターン + 複数粒径分布 + 幾何スイープ |
| まず動作確認（軽量） | `benchmark_macro10_300mm_20_generate_size_models_mix_param_sweep_v1_smoke` | 20サンプルのみ生成 |

### 3.2 `doctor`（設定検証）
```bash
python -m synthlab.cli.main process=doctor seed=1
```

### 3.3 `generate`（生成）
```bash
python -m synthlab.cli.main \
  --config-path conf/benchmarks/wafer_particles \
  --config-name benchmark_macro10_300mm_20_generate_size_models_mix_param_sweep_v1_smoke \
  seed=1
```

生成結果は `runs/` 配下に作成されます。最新runを確認する例:

```bash
ls -1dt runs/* | head -n 5
```

### 3.4 `qc`（品質統計/特徴量）
```bash
python -m synthlab.cli.main \
  process=qc seed=1 \
  input_dir="runs/<GENERATE_RUN_DIR>"
```

### 3.5 `export`（CSV/Parquet + split）
学習/評価でリークしないよう **splitは sample_id 単位**で行います。

```bash
python -m synthlab.cli.main \
  process=export seed=0 \
  wafer_particles.export.input_dir="runs/<QC_OR_GENERATE_RUN_DIR>" \
  wafer_particles.export.format=csv \
  wafer_particles.export.split.mode=ratio \
  wafer_particles.export.split.ratios.train=8 \
  wafer_particles.export.split.ratios.val=1 \
  wafer_particles.export.split.ratios.test=1
```

---

## 4. よくある詰まりポイント

| 症状 | 原因 | 対処 |
|---|---|---|
| `--config-path/--config-name` が認識されない | CLIがoverride-only実装 | `process=generate ...` 形式で全て指定（config_conventions.md参照） |
| 粒径単位が混乱 | um/nmが混在 | size_models.md の「単位規約」参照、doctorにチェックを追加 |
| 生成が遅い | 粒子数/サンプル数が大きい | smoke configで先に確認、必要なら並列化タスクを起票 |

