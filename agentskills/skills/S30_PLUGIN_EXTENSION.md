# S30 — Plugin Extension & Registry

## 目的
- 新しいパターン/サイズモデル/メトリクス/可視化を “増殖可能な形” で追加する
- if/else を増やさず、registry による拡張を守る

## 参照（MUST）
- docs/11_PLUGIN_REGISTRY.md
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md

## 手順
1) plugin 種別を決める（pattern / size_model / metric / viz / process）
2) namespaced key を決める
   - 例: `wafer_particles.pattern.ring_narrow`
3) 実装を 1ファイル 1責務で追加
4) registry に登録（重複登録防止）
5) Hydra config を追加（conf/ group）
6) スモークテスト追加（再現性 + 最低1サンプル生成/計算）

## 事故りやすい点
- registry を通さず直接 import/呼び出しを増やす
- plugin がグローバル乱数を触る（再現性崩壊）
- 1 plugin が複数責務を持ち巨大化

## DoD
- [ ] registry 経由で解決できる
- [ ] config から選べる
- [ ] seed で再現できる
