# SynthLab (Synthetic Data Platform) — Wafer Particle Domain v0

本リポジトリは「擬似データ生成」を核にしつつ、将来 **画像/動画/時系列/多次元空間**など別ドメインへ拡張できる共通基盤です。
最初のドメインとして **wafer_particles（ウェハ上パーティクル点群：極座標＋粒径＋ラベル）** を実装します。

## 重要な前提
- 生成・評価・可視化・学習などは **Process**（実行単位）として統一します。
- すべての実行は **Hydra（YAML）設定が真実**（source of truth）です。
- 出力は **artifact 契約**に従い、再現性（seed/設定/メタ/統計/可視化）を担保します。
- 拡張は **Plugin Registry**（登録制）で行い、コード肥大化を防ぎます。

## ディレクトリ構成（提案）
- docs/         : 不変契約（設計/運用/評価/拡張規約）
- work/         : 開発タスク（Codex/自動化で回す前提）
- agentskills/  : Codex指示を効率化する Skill Cards（手順・DoD・事故防止）
- conf/         : Hydra設定（YAML）— defaults/group/override の規約は docs/03 に従う
- src/          : 実装（synthlab パッケージ）
- tests/        : テスト（再現性/スキーマ/プロセスのスモーク）
- runs/         : 生成物（artifact出力先。git管理しない）

※ conf/src/tests 等の中身は work/tasks を起点に段階的に実装します。

## 読む順
1) docs/README.md
2) docs/00_INVARIANTS.md
3) docs/01_ARCHITECTURE.md
4) docs/03_CONFIG_CONVENTIONS.md
5) docs/04_ARTIFACTS_AND_VERSIONING.md
6) docs/10_PROCESS_CATALOG.md
7) docs/11_PLUGIN_REGISTRY.md
8) docs/09_EVALUATION_PROTOCOL.md
9) docs/05_SECURITY_SECRETS.md
10) docs/12_INTEGRATIONS_READY.md

## Zip化（例）
- mac/linux:
  - `zip -r synthlab_scaffold.zip docs work agentskills README.md`
- Windows(PowerShell):
  - `Compress-Archive -Path docs,work,agentskills,README.md -DestinationPath synthlab_scaffold.zip`

（実装ファイルも含める場合は conf/src/tests も追加）
