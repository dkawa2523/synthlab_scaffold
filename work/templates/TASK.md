# TASK: <id> <title>

## Summary
- 何を作るか（1〜3行）
- なぜ必要か（目的/背景）

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/...
- （このタスク固有に参照必須の docs を列挙）

## Scope
- このタスクでやること（箇条書き）
- このタスクで **やらない**こと（Non-goals）

## Inputs / Outputs
- Inputs:
- Outputs:
- Artifactへの影響（新規ファイル/スキーマ変更の有無）

## Acceptance Criteria (MUST)
- [ ] 条件1（観測可能/テスト可能）
- [ ] 条件2
- [ ] 条件3

## Verification (MUST)
- 手順（コマンド例）
- 期待される出力（ファイル/ログ/メトリクス）

## Dependencies
- depends_on: [Txxxx, ...]  # 順番待ち（blockedではない）
- blocked: <true/false>
- blocking_reason: （blockedの場合のみ）
- unblocks: [Txxxx, ...]    # 解除タスクの場合のみ

## Implementation Notes
- 実装の方針
- 既存コードへの追加点
- 破壊的変更がある場合の移行方針（blocked運用）

## Definition of Done (DoD)
- [ ] テスト
- [ ] docs更新（必要なら）
- [ ] artifact契約に適合
