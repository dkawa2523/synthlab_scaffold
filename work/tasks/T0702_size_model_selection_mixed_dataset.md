# TASK: T0702 データセット内で複数サイズ分布を混在させる（size_model_selection） (P0)

## Why
ベンチマークや異常検出用途では、データセット内に **複数の粒径分布**が混在する状況を再現したいです。

例:
- 通常時: gaussian / lognormal / weibull が混在
- 異常時: pareto（重尾）や mixture-tail が混入

これを **Hydra設定だけ**で制御できるようにし、
生成データセットに「どのサイズ分布で生成したか」を追跡できるようにします。

## Contracts
- docs/00_INVARIANTS.md（再現性）
- docs/03_CONFIG_CONVENTIONS.md（Hydra group/override）
- docs/04_ARTIFACTS_AND_VERSIONING.md（追跡可能性）
- docs/11_PLUGIN_REGISTRY.md（拡張規約）

## Scope
1) `wafer_particles.size_models` を後方互換のまま拡張
   - 既存: `size_models.type: gaussian` の単一指定
   - 新規: `size_models.selection` を指定した場合は **サンプルごと**に分布タイプを選択できる

2) 新しい設定スキーマ（案）
```yaml
wafer_particles:
  size_models:
    selection:
      mode: ratio   # ratio|list|single（最低 ratio を実装）
      shuffle: true
      ratios:
        gaussian: 1.0
        lognormal: 1.0
        weibull: 1.0
        pareto: 0.2
    models:
      gaussian: { ... }
      lognormal: { ... }
      weibull: { ... }
      pareto: { ... }
```

3) 選択ロジック
- label_selection と同様に `ratio` で n_samples 分の割当てを作り、shuffle可能
- 同じ seed で **完全再現**すること（生成順序の変化で変わらない設計が望ましい）

4) 出力追跡
- samplesテーブルに以下を保存（詳細はT0704で整理）
  - `size_model`（例: "lognormal"）
  - `size_params_json`（そのサンプルで採用されたパラメータをJSON保存）

## Non-goals
- 既存の label_selection を size_models に流用しない（コード共有はOKだが意味的には別コンポーネント）
- per-particle で分布タイプを変える（将来のmixtureで対応）

## Acceptance Criteria
- [ ] `size_models.selection` を指定すると、サンプルごとに異なるサイズ分布タイプが使われる
- [ ] ratiosに従って分布タイプが概ね割当てられる（seed固定で決定的）
- [ ] `size_models.type` 単一指定の既存挙動は壊れない
- [ ] 選択された size_model 名が samples に記録される（T0704と整合）

## Implementation Notes
- `ratio`モードは「カテゴリ配列を作ってshuffleして割当て」で良い（厳密な確率過程より再現性を優先）
- `models` は各分布タイプの config を保持し、実装側は registry で `type`→class を解決する
- type名の表記（gaussian/lognormal/...）は docs/11_PLUGIN_REGISTRY.md と一貫させる

## Verification
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=1
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_1k_generate_size_models_mix seed=42
```
生成後、samples で `size_model` 列が複数値を持つことを確認。
