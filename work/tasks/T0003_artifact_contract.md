# TASK: T0003 Artifact契約（run dir / meta / config snapshot / manifest）の実装

## Contracts
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/00_INVARIANTS.md

## Scope
- `ArtifactWriter/Reader` 的なユーティリティ（framework）を作成
- resolved.yaml / overrides.txt / meta.json を必ず保存
- `config_hash` を算出して meta に入れる
- `README.md`（run要約）生成は任意

## Acceptance Criteria
- [ ] すべての Process が同じ方法で artifact を作れる
- [ ] meta.json の必須フィールドが揃う（docs/04）
- [ ] 生成物が run dir 外へ出ない

## Verification
- doctor を実行して meta/config が出力されること
- config_hash が安定（同一resolvedで同じ）

## DoD
- [ ] テスト（最低1つ：config_hash安定性）
