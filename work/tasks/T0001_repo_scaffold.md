# TASK: T0001 リポジトリ骨格と最小CLI/Processディスパッチャの作成

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/01_ARCHITECTURE.md
- docs/10_PROCESS_CATALOG.md

## Scope
- `src/synthlab/` の骨格（framework/domains/ の空実装）
- 単一 entrypoint（例：`python -m synthlab.cli.main process=...`）で Process を切替
- process=doctor の最小実装（後で詳細化）

## Non-goals
- 本格的な生成/QC/viz 実装（別タスク）
- 外部MLOps連携

## Acceptance Criteria
- [ ] `python -m synthlab.cli.main --help` が動く
- [ ] `process=doctor` が run artifact を作り meta を出力する（最低限）
- [ ] 依存方向が docs/01 に反しない

## Verification
- `python -m synthlab.cli.main process=doctor seed=1`
- runs/ 配下に artifact ができ、meta/meta.json と config/resolved.yaml が存在する

## Implementation Notes
- Hydra導入は T0002 だが、T0001 では CLI の入口と “Process呼び出しの形” を固定する
- Hydra main の導入タイミングは実装者裁量だが、docs/00 の「configが真実」は必ず守る

## DoD
- [ ] 最小のプロジェクト構造が作成される
- [ ] doctor が artifact 契約の雛形を満たす
