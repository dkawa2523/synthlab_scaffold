# S20 — Hydra Config Conventions

## 目的
- Hydra（YAML）で設定を拡張しても破綻しないようにする
- defaults/group/override/run dir/seed を不変契約に沿って維持

## 参照（MUST）
- docs/03_CONFIG_CONVENTIONS.md
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## 手順
1) 追加したい設定を “group” に落とす
   - domain/process/wafer_particles/patterns/size_models/qc/viz/io など
2) defaults を更新
   - 既定値を増やすときは互換性に注意（既存runの再現性）
3) override を想定してキー設計
   - 例: `wafer_particles.n_samples=10000`
4) seed の扱い
   - root seed 以外を増やさない
5) resolved config の保存確認（artifact）

## 事故りやすい点
- config key の “意味” を変える（互換性崩壊）
- run dir を勝手に変えて比較不能にする
- 例外的にJSONを混ぜる（設定が分散）

## DoD
- [ ] conf/ 構造が docs/03 に沿う
- [ ] override 例が通る
- [ ] resolved.yaml が artifact に保存される
