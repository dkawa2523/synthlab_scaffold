# TASK: T0007 process=generate（大量生成と出力）

## Contracts
- docs/10_PROCESS_CATALOG.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/03_CONFIG_CONVENTIONS.md

## Scope
- 生成枚数（n_samples）を指定して samples/particles を生成
- ラベル選択を指定できる（例：割合、固定リスト、ランダム）
- 出力（parquet/csv）を IO config で切替
- manifest の作成（ファイル、行数、label分布）

## Acceptance Criteria
- [ ] 数千〜数万サンプルをバッチ生成できる（性能はP1で最適化しても良い）
- [ ] artifact 契約を満たす（config/meta/data/manifest）
- [ ] label比率指定が機能する

## Verification
- `process=generate wafer_particles.n_samples=1000 ...`
- data/particles.parquet と data/samples.parquet ができる
- manifest に label 集計が入る
