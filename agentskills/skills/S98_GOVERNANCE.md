# S98 — Governance: Tests/Review/Release

## 目的
- “何十回も Codex で反復開発” しても品質が落ちないようにする
- テスト/レビュー/DoD を統一する

## 参照（MUST）
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## 手順
1) 変更が入ったら必ずテスト観点を追加
   - 再現性
   - スキーマ
   - スモーク（generate→qc→viz）
2) PRレビュー観点（手動でもOK）
   - 依存方向が壊れていない
   - if/else 増殖していない（plugin化されている）
   - artifact契約が守られている
3) リリース/配布を想定し、README/例を更新

## 事故りやすい点
- “動いたからOK” でテストが付かない
- schema を変えたのに schema_version を変えない

## DoD
- [ ] `pytest` が通る
- [ ] 主要導線（generate→qc→viz）が再現できる
- [ ] docs との整合が取れている
