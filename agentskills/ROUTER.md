# AgentSkills ROUTER — タスクタイプ → 参照スキル

Codex に指示を出す前に「タスクの種類」を決め、この ROUTER に従って skill card を参照します。
各 TASK.md は skills を持つので、基本は queue.json に従います。

## タスクタイプ別ルーティング
- アーキテクチャ/不変条件/依存方向の変更:
  - S10_ARCHITECTURE
- Hydra設定/コンフィグ追加/override/seed/run dir:
  - S20_HYDRA_CONFIG
- Process実装（generate/qc/viz/export/train/eval/doctor/leaderboard）:
  - S40_PROCESS_IMPLEMENTATION
- Artifact/スキーマ/IO/manifest/versioning:
  - S50_ARTIFACT_AND_IO
- Plugin追加（pattern/size/metric/viz）・registry運用:
  - S30_PLUGIN_EXTENSION
- QC/評価/リーク/比較可能性:
  - S60_EVALUATION_QC
- 可視化/解析レポート/統計の読みやすさ:
  - S70_VISUALIZATION_DS
- セキュリティ/秘密情報/権限/実測データ:
  - S95_SECURITY
- テスト/品質/レビュー/リリース運用:
  - S98_GOVERNANCE

## 運用ルール
- まず docs/00_INVARIANTS.md を読む
- 迷ったら S10 を起点に “依存方向” と “拡張点” を確認する
