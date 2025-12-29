# TASK: T0005 基礎パターンジェネレータ実装（細粒度＋カテゴリ拡張）

## Contracts
- docs/11_PLUGIN_REGISTRY.md
- docs/00_INVARIANTS.md
- docs/09_EVALUATION_PROTOCOL.md（期待特徴ルールの方向性）

## Scope
- 以下を Plugin として実装（まずは wafer_particles.pattern.*）
  - ring_narrow / ring_wide（リング幅）
  - edge_sector（左右/角度範囲/エッジ距離：パラメータで拡張）
  - scratch（角度カテゴリ：horizontal/diagonal 等を taxonomy で表現）
  - radial_lines（本数/角度/中心固定）
  - hotspot（center/edge/random 等）
  - random_uniform / random_edge_biased
  - composite（複数パターンを合成できる枠）
- taxonomy_v1.yaml に “細粒度ラベル定義” の雛形（期待特徴のTODO含む）

## Acceptance Criteria
- [ ] registry 経由で generator を選べる
- [ ] 同一 seed で同一出力（再現性）
- [ ] パラメータを変えると分布が変わる（最小確認）

## Verification
- generate を小規模に走らせ、labelごとに 1サンプル生成→viz で確認

## DoD
- [ ] 各パターンのスモークテスト
