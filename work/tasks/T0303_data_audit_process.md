# TASK: T0303 データ監査（Data Audit）Process導入（重複/欠損/範囲外/リークの自動検知）(P0)

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/09_EVALUATION_PROTOCOL.md
- docs/10_PROCESS_CATALOG.md

## Summary
生成データを学習に使う前に、**データ品質/リーク/スキーマ逸脱**を自動検知する `process=audit`（または `process=data_audit`）を追加する。

## Scope
- 新規 Process: `process=audit` を実装
  - input: generate/export の artifact
  - output: `metrics/audit.json` + （任意）`metrics/audit_tables/*.csv`
- 監査項目（最低限）
  - 欠損: 必須列（sample_id, particle_id, r_mm, theta_rad, size_um, label）欠損検知
  - 範囲外: r<0, r>150mm（300mm wafer想定）、theta<0, theta>2π、size<=0
  - 重複: (sample_id, particle_id) 重複、同一粒子の完全重複行
  - leak/contamination の準備: split がある場合、同一 sample_id が train/val/test に跨っていないか（export artifact入力時）
- 監査結果は機械可読（JSON）で、重大度（error/warn/info）を含む
- 重大エラーがある場合、Process は非ゼロ終了（= Verification で検出できる）にするか、`audit_failed=true` を出力して run_loop が検知できるようにする

## Non-goals
- 会社規定のセキュリティ監査（docs/05は別）
- 大規模統計の高度な外れ値検出（P1で拡張可）

## Acceptance Criteria
- [ ] `process=audit` が generate/export artifact を入力に取り、監査レポートを出力する
- [ ] 明示的に壊したデータ（テスト内で注入）を検知し、error を報告できる
- [ ] 学習利用を想定した最低限の監査が揃う

## Verification
- `pytest -q -k T0303`

## Implementation Notes
- テストで “壊れた行” を少数注入し、検知できることを保証する（再現性のため seed を固定）
- docs/00 の “skew禁止” を強化する観点で、変換の二重実装なども監査対象に含めてもよい
