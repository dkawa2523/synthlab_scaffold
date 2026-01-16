# Size Models（粒径分布）

粒径（particle size）は、工程・起源（CMP/剥離/残渣/粉砕/混入）により分布が変わります。
本フレームワークでは、粒径分布を **プラグイン（SizeModel）**として扱い、設定で切り替え・混在できます。

---

## 1. 目的別に「何が必要か」

| 目的 | 必須機能 | なぜ必要か |
|---|---|---|
| 合成データ生成 | 現実的な分布（lognormal等） + clamp | “使える疑似データ”の品質 |
| 学習データ増強 | per_sample で分布パラメータを振る | 過学習抑制、頑健性 |
| 異常検出 | heavy-tail（pareto等）を少量混ぜる | 異常シナリオの合成 |

---

## 2. 実装済み分布モデル（代表）

> 実装の真実は `conf/wafer_particles/size_models/` と `domains/.../size_models/` です。

| モデル | PDF（概念） | パラメータ | 特徴 | 代表シナリオ |
|---|---|---|---|---|
| gaussian | N(μ,σ²) | `mean_um`, `std_um` | 対称・裾が軽い | 制御粒子の近似 |
| lognormal | exp(N(μ,σ²)) | `mu_log`, `sigma_log` | 右裾が長い | 粒径分布の定番 |
| weibull | k/λ(x/λ)^(k-1) exp(-(x/λ)^k) | `k`, `lambda` | 柔軟（破砕由来に強い） | 破片/粉砕 |
| pareto | α x_m^α x^-(α+1) | `alpha`, `x_min` | 超重尾 | 異常混入（最悪ケース） |
| mixture | Σ w_i f_i(x) | `weights`, `components` | 1サンプル内混合 | 通常＋異常 |

---

## 3. 重要機能：per_sample（サンプルごとに分布パラメータを変える）

### 3.1 なぜ必要？
「全体でガウス」ではなく、**サンプル（ウェハ）ごとに μ/σ が違う**状況を表現できます。

- 生成されたデータセット全体としては「ガウスの混合（Mixture of Gaussians）」になる
- 工程差・装置差・時系列揺らぎの疑似表現として有効
- 異常検出では「パラメータが逸脱したサンプル」を作りやすい

### 3.2 設定例（ガウス：平均20–800nm、標準偏差20–100nm）
```yaml
wafer_particles:
  size_models:
    type: gaussian
    per_sample: true
    min_um: 0.01
    max_um: 1.0
    mean_um: {dist: uniform, low: 0.02, high: 0.8}
    std_um:  {dist: uniform, low: 0.02, high: 0.1}
```

### 3.3 運用上の必須: パラメータ記録
per_sample では、サンプルごとに使ったパラメータが異なるため、追跡できないと解析不能になります。

**必須出力（samplesテーブル）**
- `size_model`
- `size_params_json`（分布パラメータをJSON文字列で保存）

---

## 4. 重要機能：selection（データセット内で複数分布を混在）

### 4.1 目的
- 「通常はlognormal、5%だけpareto」などの **異常注入**
- モデルが特定分布に過学習しないよう **多様な分布**で学習させる
- 分布の切り替わりを **メタ情報**として保存して、後で分析

### 4.2 設定例（比率で割当）
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

## 5. clamp（min/max）のルール

| ルール | 理由 |
|---|---|
| すべてのモデルは `min_um/max_um` でクランプ | 物理・計測範囲を逸脱した値を禁止 |
| clampの単位は統一（推奨: um） | um/nm混乱を防ぐ |
| doctor で `min < max` と桁妥当性を検証 | 誤設定で学習が壊れるのを防ぐ |

---

## 6. QC（粒径分布の特徴量）との関係

異常検出・特徴増強では、粒径分布の統計量（平均/分散/歪度/尖度/percentiles）が重要です。

| 指標 | 使いどころ |
|---|---|
| mean/std | 代表値・ばらつき |
| skew/kurtosis | heavy-tail の検知 |
| p10/p50/p90 | 尾の厚さ、比較しやすい |
| KS統計（将来） | 実測 vs 合成の距離 |

---

## 7. 新しい分布を追加する手順（概要）
詳細は developer_guide.md。

1. `domains/.../size_models/` にサンプラ実装を追加
2. `conf/.../size_models/<name>.yaml` を追加
3. selection対象に追加（必要なら）
4. `doctor` にパラメータ範囲チェックを追加
5. `tests` に分布生成テスト（clamp・再現性・heavy-tail）を追加
6. docs（このファイル）に追記
