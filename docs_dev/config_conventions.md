# Config Conventions (Hydra)

このドキュメントは、Hydra設定（YAML）の **設計規約**と、運用で事故りやすいポイントをまとめます。

> 原則: **設定（YAML）が真実**。コードにハードコードしない。

---

## 1. Hydra の基本

### 1.1 設定合成の考え方
Hydraは `defaults` により複数のYAMLを合成して最終設定（resolved config）を作ります。

- `conf/config.yaml` が入口（root config）
- `domain`, `process`, `profiles`, `patterns`, `size_models` などを defaults で選ぶ
- CLI override（`key=value`）で一時的に上書きできる
- 実行時に合成された設定は run の `meta/resolved.yaml` に保存される（再現性の根幹）

### 1.2 コマンドの基本形
#### (A) config-path / config-name 方式（Hydra標準）
```bash
python -m synthlab.cli.main \
  --config-path conf/benchmarks/wafer_particles \
  --config-name benchmark_macro10_300mm_1k_generate_size_models_mix_param_sweep_v1 \
  seed=42
```

#### (B) override-only 方式（環境によってはこちら）
```bash
python -m synthlab.cli.main \
  process=generate domain=wafer_particles seed=42 \
  wafer_particles.n_samples=1000
```

> どちらが有効かは `python -m synthlab.cli.main -h` の usage で判定してください。

---

## 2. 命名規約（推奨）

### 2.1 ベンチマーク設定ファイル
`conf/benchmarks/wafer_particles/` に **再現可能なレシピ**として固定します。

| 要素 | 例 | ルール |
|---|---|---|
| 目的 | `benchmark` | benchmark は必ず先頭 |
| ラベル粒度 | `macro10` | macro数を明示 |
| wafer条件 | `300mm` | 直径で書く（半径は設定内） |
| 件数 | `1k` | `20`（smoke）なども可 |
| 生成内容 | `generate` / `export` | process名を含める |
| 特徴 | `size_models_mix` / `param_sweep` | 重要な差分を列挙 |
| バージョン | `v1` | 破壊的変更時は上げる |

例:
- `benchmark_macro10_300mm_1k_generate_size_models_mix_param_sweep_v1.yaml`
- `benchmark_macro10_300mm_20_generate_size_models_mix_param_sweep_v1_smoke.yaml`

---

## 3. 単位と正規化（必須）

### 3.1 位置
| 量 | 推奨単位 | 備考 |
|---|---|---|
| wafer半径 | `mm` | 300mm wafer → `wafer_radius_mm=150` |
| r | `mm` | `0 <= r_mm <= wafer_radius_mm` |
| θ | `rad` | 定義域はプロジェクトで統一（推奨: `[0, 2π)`） |

### 3.2 粒径
| 量 | 推奨単位 | 備考 |
|---|---|---|
| size | `um`（内部） | 設定に `min_um/max_um` を持たせる |
| 出力 | `size_um` or `size_nm` | CSVにどちらで出るかは schema を真実として統一 |

> 単位混乱は最も致命的です。doctor で `min < max` や桁の妥当性チェックを必須にしてください。

---

## 4. param_space（パラメータを分布で振る）

### 4.1 目的
- **サンプル間多様性**（形状・粒子数・密度・角度など）を確保
- モデルが固定形状に過学習するのを防ぐ
- 異常検出時に “どの程度ズレたら異常か” を評価できる

### 4.2 典型的な指定例
```yaml
# 粒子数を 10〜200 の範囲で振る（分布は例）
wafer_particles:
  n_particles:
    dist: truncnorm
    mean: 80
    std: 40
    min: 10
    max: 200
```

```yaml
# スクラッチ長さ（mm）と幅（mm）を振る
C07_StraightLine:
  length_mm: {dist: uniform, low: 10, high: 100}
  width_mm:  {dist: uniform, low: 5,  high: 10}
```

> 実際のキー名は pattern 実装の `params_schema()` / conf の patterns YAML を真実として合わせてください。

---

## 5. size_models（粒径分布）設定

### 5.1 per_sample（サンプルごとに平均・分散が違う）
ガウス分布の例（20–800nm, 20–100nm）:

```yaml
wafer_particles:
  size_models:
    type: gaussian
    per_sample: true
    min_um: 0.01   # 10nm
    max_um: 1.0    # 1000nm
    mean_um: {dist: uniform, low: 0.02, high: 0.8}
    std_um:  {dist: uniform, low: 0.02, high: 0.1}
```

必須:
- `samples` に `size_model` / `size_params_json` を保存（後から追跡できる）

### 5.2 selection（データセット内で複数分布を混在）
```yaml
wafer_particles:
  size_model_selection:
    mode: ratio
    ratios:
      gaussian:  0.50
      lognormal: 0.25
      weibull:   0.20
      pareto:    0.05
```

---

## 6. 乱数 seed の規約

| ルール | 理由 |
|---|---|
| seed は必ず指定 | 再現性/比較可能性の根幹 |
| seed を隠さない | 生成runの `meta/resolved.yaml` に必ず記録 |
| seed を process ごとに変えるのは慎重に | generate と export で seed を変えるとsplitが変わる可能性がある |

推奨:
- generate と export は **固定seed**で運用（比較や再生成が必要な場合）

---

## 7. 互換性（破壊的変更を避ける）

### 7.1 禁止事項
- 既存キーの意味を変える（例: `size_um` の単位を変える）
- 出力カラム名を黙って変える
- run構造（artifacts契約）を黙って変える

### 7.2 どうしても変える場合
- config名に `v2` を作る
- 旧版も残して比較可能にする
- `docs/` に移行ガイドを書く
- `tests/` に後方互換テストを置く

