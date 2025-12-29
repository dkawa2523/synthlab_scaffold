# TASK: T0004 wafer_particles ドメインのスキーマ定義

## Contracts
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/00_INVARIANTS.md

## Scope
- particles テーブル、samples テーブルのスキーマ定義（列名/型/必須）
- schema_version = wafer_particles.v1 を確定
- 変換（r,theta→x,y）の単一関数化（skew防止）

## Acceptance Criteria
- [ ] スキーマがコード（dataclass等）と docs/04 に一致
- [ ] schema_version が meta/manifest に入る
- [ ] 変換関数が 1箇所に集約

## Verification
- generate の仮データを少量作り、schema validate が通る（簡易でOK）

## DoD
- [ ] スキーマ検証の最小テスト（必須列/型）
