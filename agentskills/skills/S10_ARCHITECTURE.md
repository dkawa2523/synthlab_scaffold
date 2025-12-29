# S10 — Architecture & Invariants (Architect)

## 目的
- 構造が肥大化しないように **依存方向**と**拡張点**を守る
- docs/00（不変契約）を破らない変更計画を作る
- 将来ドメイン（画像/動画/時系列）にも耐える骨格を維持する

## 参照（MUST）
- docs/00_INVARIANTS.md
- docs/01_ARCHITECTURE.md
- docs/11_PLUGIN_REGISTRY.md

## 手順（やること）
1) 変更要求を “分類” する
   - (A) 新機能追加（plugin/新process）なのか
   - (B) 既存契約の変更（schema/評価/依存方向）なのか
2) 依存方向をチェック
   - Hydra依存が Domain/Plugin に侵入していないか
   - 下位層が上位層を import していないか
3) 拡張点を registry で吸収できるか検討
   - if/else を増やさず plugin 化できる形に変換
4) 互換性・移行計画を作る
   - schema_version が必要か
   - artifact の互換性（旧runが読めるか）
5) docs を更新する（必要な場合）
   - 不変契約に影響するなら blocked運用

## 事故りやすい点
- 「とりあえず便利だから」Domain/Plugin で Hydra を直接読む
- 1ファイルにロジックを寄せて巨大化
- schema（列の意味）を変更したのに schema_version を変えない

## Definition of Done（DoD）
- [ ] 依存方向が docs/01 と一致
- [ ] 拡張は registry を通る
- [ ] 互換性が壊れる場合は blocked運用がある
- [ ] docs が更新され、タスクがdocsを根拠にできる

## よくある差分（テンプレ）
- 新Domain追加:
  - framework は触らず `domains/<new>/` を追加し、process から選べるようにする
- schema変更:
  - `schema_version` を上げる or 旧スキーマ読み込み互換レイヤを追加
