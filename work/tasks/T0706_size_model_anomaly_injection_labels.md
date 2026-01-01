# TASK: T0706 粒径分布ベースの異常注入/ラベル付与（評価用） (P1)

## Why
異常検出の評価には、異常サンプルが既知のベンチマークがあると強いです。
粒径分布は異常（大粒子混入、重尾化）の代表的要因のため、
生成時に「異常サイズ分布サンプル」を一定割合で混入し、ラベル付与できると便利です。

## Contracts
- docs/04_ARTIFACTS_AND_VERSIONING.md（ラベルの保存）
- docs/00_INVARIANTS.md（再現性）
- docs/03_CONFIG_CONVENTIONS.md（設定が真実）

## Scope
1) `wafer_particles.size_models.selection` に異常ラベル機能を追加（案）
```yaml
wafer_particles:
  size_models:
    selection:
      mode: ratio
      ratios: {...}
      anomaly_types: ["pareto", "mixture_tail"]
      anomaly_label_name: "is_size_anomaly"
```

2) 生成時に samples テーブルへ以下を追加
- `is_size_anomaly` : 0/1
- `size_anomaly_type` : str（例: "pareto"）

3) export（CSV）にも同列を出す（T0704と整合）

4) ベンチマーク用サンプル設定（T0707でconfig提供）
- 例: 95% baseline + 5% pareto or mixture_tail

## Non-goals
- 異常検出モデルそのものの実装
- 実測データからの異常自動推定（将来タスク）

## Acceptance Criteria
- [ ] anomaly_types に含まれる size_model が選ばれたサンプルに `is_size_anomaly=1` が付く
- [ ] seed固定で同一の異常割当てが再現される
- [ ] anomaly_types 未指定の場合は列が無い or 全て0（方針をdoctorと合わせる）

## Implementation Notes
- 既存の labeling_apply / taxonomy と衝突しない列名にする
- `anomaly_label_name` はユーザが変更可能にする（衝突回避）

## Verification
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_anomaly_size_models_mix_300mm_1k seed=42
```
生成後、samplesで `is_size_anomaly` が 0/1 を含むことを確認。
