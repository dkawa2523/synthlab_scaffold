# Codex 指示テンプレ（毎回コピペして使う）

## 1) Target Task
- Task ID: <例: T0007>
- Task file: work/tasks/<...>.md

## 2) Contracts (必読)
- docs/00_INVARIANTS.md
- docs/<...>
- （queue.json の contracts をすべて列挙）

## 3) Skills to follow
- agentskills/skills/<...>.md
- （queue.json の skills をすべて列挙）

## 4) Scope
- 変更してよいディレクトリ: <例: src/, conf/, tests/>
- 変更禁止: docs/00_INVARIANTS.md に抵触する変更（seed/副作用/巨大if等）

## 5) Acceptance Criteria / Verification
- TASK.md の該当セクションをそのまま貼る

## 6) Output要求（Codexに求める成果物）
- 変更ファイル一覧
- 実行コマンド
- 期待される生成物（artifact）
