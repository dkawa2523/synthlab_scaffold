# 11_PLUGIN_REGISTRY — 拡張（モデル/特徴量/Process）登録規約

## 1. 目的
- 新しいパターン/サイズモデル/メトリクス/可視化/Process を追加しても
  - if/else が肥大化しない
  - ディレクトリが無秩序にならない
  - レビューが容易
を保証する。

## 2. Plugin種別（v1）
- PatternGenerator（点座標を生成）
- SizeModel（粒径を割り当て）
- Metric（QC指標）
- Visualizer（プロット生成）
- Process（generate/qc/viz/export/train…）

## 3. 登録の原則（MUST）
- plugin は **名前（key）**で登録される
- key は namespaced にする（衝突防止）
  - 例: `wafer_particles.pattern.ring_narrow`
- plugin は **純関数的**に扱う（入力+cfg+rng → 出力）
- plugin が Hydra/OmegaConf に依存しない（cfgはPythonオブジェクト/辞書として受け取る）

## 4. Interface（概念）
### PatternGenerator
- input: `cfg`, `rng`, `sample_ctx`
- output: `particles`（r,theta など）

### SizeModel
- input: `cfg`, `rng`, `particles`
- output: `particles`（size_um 列追加）

### Metric
- input: `cfg`, `tables`
- output: dict（json化可能）

### Visualizer
- input: `cfg`, `tables`, `out_dir`
- output: files（png/html）

## 5. 追加手順（MUST）
1) 実装を追加（domains/<domain>/...）
2) registry に登録（decorator または register関数）
3) Hydra config を追加（conf/ の group）
4) tests を追加（再現性/最低限のスモーク）
5) docs（taxonomy/期待特徴）を更新（必要なら）

## 6. “巨大ファイル化” 防止ルール
- 1ファイル 300行を超える場合、分割を検討
- patterns は 1パターン=1ファイル を基本（ただし超小規模ならまとめてもよい）
- registry は “登録だけ” を持ち、実装ロジックを置かない

## 7. TODO
- entrypoints（setuptools entry points）による外部pluginロード: TODO（P1以降）
