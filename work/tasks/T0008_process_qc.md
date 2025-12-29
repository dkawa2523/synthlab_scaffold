# TASK: T0008 process=qc（統計/QCメトリクス/期待特徴ルール）

## Contracts
- docs/09_EVALUATION_PROTOCOL.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## Scope
- hist_r / hist_theta / size stats / n_particles stats を label別に計算
- “期待特徴ルール” を taxonomy_v1.yaml から読み、ルールチェックを実装（P0は簡易でOK）
- metrics/qc.json + label_summary.csv を出力

## Acceptance Criteria
- [ ] QC出力が機械可読（json/csv）
- [ ] 比較可能な bin 定義が config に固定
- [ ] ルール違反が検出できる（最低1例）

## Verification
- generate→qc の順に実行し metrics が出る
