# TASK: T0011 テスト（再現性/スキーマ/スモーク）と process=doctor

## Contracts
- docs/00_INVARIANTS.md
- docs/10_PROCESS_CATALOG.md

## Scope
- 再現性テスト（同一seedで同一出力）
- スキーマテスト（必須列）
- 最小スモーク（generate→qc→viz）
- doctor の拡充（依存/バージョン/設定チェック）

## Acceptance Criteria
- [ ] CI無しでもローカルで `pytest` が通る設計
- [ ] doctor が “事故りやすい点” を検知できる（seed未設定など）

## Verification
- `pytest -q`
- `process=doctor` 実行で meta/doctor.json が生成される
