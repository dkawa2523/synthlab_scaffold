# TASK: T0708 テスト/doctor拡張（サイズ分布mix・新分布） (P0)

## Why
サイズ分布の種類が増えると、設定ミス（負のsigma、paretoのalpha<=0等）で
データ品質が壊れるリスクが増えます。
autodev ループで確実に止めるため、doctor とテストを拡張します。

## Contracts
- docs/00_INVARIANTS.md（再現性）
- docs/03_CONFIG_CONVENTIONS.md（Hydra）
- docs/10_PROCESS_CATALOG.md（processの入出力）
- docs/04_ARTIFACTS_AND_VERSIONING.md（出力）

## Scope
1) doctor validation の追加
- size_models.type 単一指定:
  - gaussian: std_um>0, min_um<max_um
  - lognormal: sigma_log>0, min_um<max_um
  - weibull: k>0, lambda_um>0
  - pareto: alpha>0, xm_um>0
  - mixture: components >=1, weight>0, sum(weight)>0
- size_models.selection:
  - ratios が空でない
  - ratios 値が >=0
  - models に定義があること（未定義typeはFAIL）
  - shuffle等の型チェック

2) unit tests 追加（pytest）
- `tests/test_T0701_size_models_new_distributions.py`
  - lognormal/weibull/pareto の出力が正で clamp を満たす
- `tests/test_T0702_size_model_selection_mix.py`
  - ratios に従い size_model が複数種出る（seed固定）
- `tests/test_T0704_size_metadata_json.py`
  - size_params_json が有効なJSONで、必要キーを含む
- （任意）`tests/test_T0706_anomaly_labels.py`
  - anomaly_types に応じて is_size_anomaly が付与される

3) CI/doctor
- `python -m synthlab.cli.main process=doctor ...` がFAIL/PASSすること
- smoke config を doctored run で通す

## Acceptance Criteria
- [ ] doctor が不正設定を検知して終了できる
- [ ] pytest が全て通る
- [ ] smoke benchmark が通る

## Verification
```bash
pytest -q
python -m synthlab.cli.main process=doctor --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=1
```
