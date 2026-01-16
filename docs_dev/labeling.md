# Labeling（多層ラベル / 外部spec）

本フレームワークでは、生成時の **fineラベル（見た目パターン）** と、
運用・分析のための **macro/階層ラベル**を分離します。

- fineラベル: 生成器（Pattern）が付与（例: `C03_Ring`）
- macro/階層: 外部spec（YAML）で後付け（例: `Ring`, `Line`, `Hotspot`）

---

## 1. なぜ分離する？

| 問題 | 分離しないとどうなるか | 分離すると |
|---|---|---|
| ラベル粒度が増えすぎる | 運用不能（学習・評価・説明が破綻） | macroで集約し運用可能 |
| パターン名=原因と誤認 | 誤った結論を誘発 | “見た目”と“原因仮説”を別管理 |
| チームごとに分類軸が違う | 比較不能 | 外部specを切り替えて比較可能 |

---

## 2. labeling spec の概念スキーマ

> 実際のキーは `conf/wafer_particles/labeling/` の例を真実として合わせてください。

```yaml
version: 1
layers:
  label_macro:
    C01_Uniform: Random
    C03_Ring:    Ring
    C07_StraightLine: Line
similarity_groups:
  RingLike: [C03_Ring, K02_SemiRing_Segment, K01_Donut_Hollow]
cause_hypotheses:
  FocusRingRelated:
    description: "focus ring / covering 近傍起因の可能性"
    related_fine: [C14_EdgeSource_Spray, C15_EdgeSource_Bursty]
```

### 2.1 layers
- `layers.<new_column>` に fine→派生値のマッピングを書く
- 実行時に `labeling_apply` が `particles/samples` に列を追加する

### 2.2 similarity_groups（任意）
- 似ているパターン集合を定義
- “ラベル粒度上げすぎ”問題に対し、運用側で再編しやすい

### 2.3 cause_hypotheses（任意）
- 原因仮説をメタ情報として残す（学習ラベルとは別）
- レポート/ダッシュボードに載せる用途

---

## 3. labeling_apply の使い方

```bash
python -m synthlab.cli.main \
  process=labeling_apply seed=1 \
  input_dir="runs/<RUN_DIR>" \
  wafer_particles.labeling.spec_path="conf/wafer_particles/labeling/benchmark_macro10.yaml"
```

---

## 4. UNKNOWN の扱い

| ケース | 推奨 |
|---|---|
| specに無いfineラベルが出た | `UNKNOWN` にマッピングし、doctor/qcで警告 |
| specを更新したい | specはバージョン管理し、runに hash を保存 |
| 過去runとの比較 | spec hash が違うものは“厳密比較不可”として扱う |

---

## 5. 多層ラベル運用のベストプラクティス

| ベストプラクティス | 理由 |
|---|---|
| fineは増やしてよいが、macroは抑える（10〜数十） | 学習・説明・意思決定が回る |
| specを別リポジトリ/別フォルダに切り出す | 原因仮説の更新頻度が高い |
| similarity_groups を必ず用意 | 粒度増大への安全弁 |
| specの変更は v2 などで増分管理 | 過去runとの比較のため |
