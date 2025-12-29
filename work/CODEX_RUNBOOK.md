# Codex 反復開発ランブック

## 前提
- 不変契約: docs/00_INVARIANTS.md
- タスク台帳: work/queue.json
- スキルカード: agentskills/

## 反復ループ（毎回同じ）
1. queue.json で `todo` のタスクを選ぶ（depends_on が満たされているもの）
2. 対象タスク md を読む（Acceptance Criteria / Verification を最優先）
3. skills に対応する agentskills/skills/*.md を読む
4. agentskills/CODEX_INSTRUCTION_TEMPLATE.md を埋めて Codex に投げる
5. 変更差分を確認（ファイル/依存方向/if増殖/seed）
6. Verification を実行（TASK.md の通り）
7. 問題があれば “追加タスク” で分割して続行（大きな修正は一気にやらない）

## ブレ防止のチェック（最小）
- Hydra config が真実：resolved.yaml が artifact に出ているか
- seed が単一で注入されているか（グローバル乱数禁止）
- plugin 追加は registry 経由か（巨大if禁止）
- artifact 契約（docs/04）の構造が守られているか

## よくあるトラブル
- config が散って再現不能 → まず docs/03 に戻す
- 生成はできたが比較できない → bin定義/seed/manifest を固定（docs/09）
