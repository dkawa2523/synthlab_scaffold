# TASK: T0704 サイズ分布のメタデータ保存（samplesスキーマ/CSV export） (P0)

## Why
データセット内で複数サイズ分布を混在させる場合、
「どのサンプルがどの分布・どのパラメータで生成されたか」を追跡できないと運用不能になります。

- 生成品質の検証（distributionの意図通りか）
- 学習/異常検出のエラー解析（失敗サンプルはどの分布だったか）
- 将来的なキャリブレーション（実測に合わせたパラメータ推定）

そのため、**サンプル単位で size_model とパラメータ**を保存する必要があります。

## Contracts
- docs/04_ARTIFACTS_AND_VERSIONING.md（artifact契約）
- docs/00_INVARIANTS.md（再現性）
- docs/03_CONFIG_CONVENTIONS.md（設定が真実）
- docs/09_EVALUATION_PROTOCOL.md（比較可能性）

## Scope
1) samples テーブルに以下を追加（後方互換を壊さない）
- `size_model` : str（例: gaussian/lognormal/weibull/pareto/mixture）
- `size_params_json` : str（JSON文字列。resolved hyper-paramsを保存）
- （既にT0602で `size_mean_um` / `size_std_um` を追加している場合は維持し、gaussian以外はNaNで良い）

2) `size_params_json` の内容（最低限）
- 共通: min_um, max_um, per_sample
- gaussian: mean_um, std_um
- lognormal: mu_log, sigma_log
- weibull: k, lambda_um
- pareto: alpha, xm_um
- mixture: components（name, weight, model_type, resolved params）

3) Export（CSV）でもこの列を必ず出力する
- 出力形式がCSVの場合、samples.csv に `size_model` / `size_params_json` を含める
- 粒子データ（particles.csv）にも必要なら sample_id join で追跡可能

## Non-goals
- JSONを厳密スキーマ化（将来のschema versioningで対応）
- 既存テーブルの列名変更（互換性破壊）

## Acceptance Criteria
- [ ] 生成後の samples に `size_model` と `size_params_json` が存在する
- [ ] 生成→export(CSV)後も同じ列が出力される
- [ ] seed固定で同一runなら同一JSONが出力される（順序依存しない）

## Implementation Notes
- JSONは `json.dumps(obj, sort_keys=True, ensure_ascii=False)` を推奨（比較可能性）
- `size_params_json` は小さく保つ（巨大配列を入れない）
- 将来 `labeling_spec_hash` と同様に `size_model_spec_hash` を導入しても良いが、このタスクでは必須ではない

## Verification
```bash
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_generate_size_models_mix_smoke seed=3
python -m synthlab.cli.main --config-path conf/benchmarks/wafer_particles --config-name benchmark_macro10_300mm_20_export_size_models_mix_smoke seed=3
```
export された samples.csv を確認し、`size_model` と `size_params_json` が含まれること。
