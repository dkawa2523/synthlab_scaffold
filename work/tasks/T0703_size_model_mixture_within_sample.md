# TASK: T0703 1サンプル内の混合粒径分布（mixture size model） (P1)

## Why
実測では「通常の小粒子群 + ごく一部の大粒子（重尾）」のような **混合分布**が頻出します。
これは以下に直結します。

- 異常検出: 大粒子の混入（フィルタ破れ、剥離片混入）を評価したい
- 学習拡張: 同じパターンでも粒径分布のモード数が変わるケースを含めたい
- 合成データ: 現実に近いマルチモーダルを再現したい

T0702 は「サンプルごとに分布タイプが異なる」混在ですが、
本タスクでは **単一サンプル内で複数分布を混ぜる**機能を追加します。

## Contracts
- docs/00_INVARIANTS.md（再現性）
- docs/03_CONFIG_CONVENTIONS.md（Hydra）
- docs/11_PLUGIN_REGISTRY.md（拡張性）
- docs/04_ARTIFACTS_AND_VERSIONING.md（追跡可能性）

## Scope
1) `size_models.type: mixture` を追加
2) mixture の設定例
```yaml
wafer_particles:
  size_models:
    type: mixture
    min_um: 0.01
    max_um: 1.0
    per_sample: true   # mixture全体としての per_sample（推奨）
    components:
      - name: base
        weight: 0.95
        model:
          type: lognormal
          mu_log: {dist: uniform, low: -5.0, high: -2.0}
          sigma_log: {dist: uniform, low: 0.2, high: 0.8}
      - name: tail
        weight: 0.05
        model:
          type: pareto
          alpha: {dist: uniform, low: 1.5, high: 4.0}
          xm_um: {dist: uniform, low: 0.2, high: 0.8}
```

3) 動作
- 粒子ごとに component を多項分布で選択し、その component の分布からサイズを生成
- clamp は最終的に必ず適用
- per_sample の場合、componentモデルのハイパーパラメータは **サンプルごとに固定**でサンプルする

4) 追跡
- samples に `size_model="mixture"` を記録
- `size_params_json` に component情報（weight, type, resolved params）を保存（T0704と整合）

## Acceptance Criteria
- [ ] `type: mixture` が指定できる
- [ ] components weights が 0<weight and sum≈1 を満たす（doctorで検証）
- [ ] サンプル内で混合分布が生成される（tail成分が一定割合で含まれる）
- [ ] seed固定で再現性がある

## Implementation Notes
- mixture自体も size model registry の1つとして実装する
- componentの `model` は既存 size model と同じ config を再利用する（registryで解決）
- weightsの正規化は実装側で許可（合計が1でない場合は正規化 or doctorでFAIL。方針はdoctorで統一）

## Verification
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=2
```
