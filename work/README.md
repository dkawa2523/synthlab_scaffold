# work/ — Codex運用の入口

## 目的
- `work/queue.json` を唯一の “タスク台帳” として、何十回も Codex で反復してもブレない開発を行う

## 運用（推奨）
1) `work/queue.json` で `status=todo` かつ `depends_on` が満たされたタスクを選ぶ
2) タスク md を読む（Acceptance Criteria と Verification を必ず確認）
3) `skills` に書かれた AgentSkill を参照して、Codex への指示を作る
4) 実装→Verification→完了条件を満たしたら、queue.json の status を更新（任意）

## Codex指示テンプレ（例）
- 対象: T0007
- 参照docs: docs/10, docs/04, docs/03, docs/00
- 参照skills: S40, S50, S20
- 実装範囲: src/ と conf/（必要なら tests/）
- 禁止: グローバル乱数、巨大if、artifact契約違反

## 例：codex-cli への投げ方（擬似）
1) `work/tasks/T0007_process_generate.md` を開く
2) その内容をベースに Codex に「実装指示」を出す
3) 変更差分が大きい場合は PR 単位に分割して反復する
