# TASK: T0202 複合パターン体系化：Composite DSL + プリセットライブラリ（P0）

## Summary
- 現状の `composite` を “設定だけで拡張できる” 形に強化し、**複合パターンを体系化**する。
- 代表的な複合パターン（リング＋ホットスポット、セクタ＋スクラッチ等）を **プリセットYAML** として追加する。

## Contracts (MUST READ)
- docs/00_INVARIANTS.md（再現性・skew禁止）
- docs/03_CONFIG_CONVENTIONS.md（Hydra group）
- docs/04_ARTIFACTS_AND_VERSIONING.md（component列の扱い）
- docs/11_PLUGIN_REGISTRY.md（拡張はplugin/registryで）

## Scope
- Composite DSL を定義（Hydra YAMLで表現）
  - components: list
    - `pattern`（registry key）
    - `weight`（粒子数比 or 出現比）
    - `cfg`（そのpatternへの部分設定override）
    - `transform`（任意、component毎の座標変換）
      - `rotate_theta_rad`（定数 or 範囲）
      - `mirror_theta`（bool）
      - `radial_scale`（定数 or 範囲）
      - `theta_jitter_std` / `r_jitter_std`（任意、component内ジッタ）
- `composite` generator を拡張し、上記 DSL を解釈して生成できるようにする
- 生成データに component 情報を必ず残す（後方互換で列追加OK）
  - particles: `component`（既存があれば維持） + `component_id`（任意）
  - samples: `components_json`（任意、JSON文字列）
- プリセットYAMLを最低5個追加（例）
  - ring_hotspot_center
  - ring_hotspot_edge
  - edge_sector_plus_scratch
  - dual_ring
  - multi_hotspot
- taxonomy_v2（T0201）と整合するよう、複合の coarse/family を整理（ラベル追加は慎重に。基本は composite family で包括）

## Non-goals
- 画像ベース合成（ここでは点群のみ）
- UI（streamlit等）は別タスク

## Inputs / Outputs
- Inputs:
  - 既存 composite 実装
- Outputs:
  - conf/wafer_particles/patterns/composite_presets/*.yaml（または同等のgroup）
  - composite DSL 対応のコード
  - particles/samples の component メタ出力
  - tests（プリセット生成の再現性）

## Acceptance Criteria (MUST)
- [ ] プリセットYAMLを指定して `process=generate` できる（最低2種）
- [ ] 1サンプル内で `particles.component` が2種類以上存在する（複合になっている）
- [ ] `process=viz` が component 情報を利用して見分けやすい可視化を出せる（最低限、凡例 or 色分け）
- [ ] 同一seedで同一出力（component割当も再現）

## Verification (MUST)
1) composite preset で小規模生成
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=5 wafer_particles/patterns=composite_ring_hotspot_center seed=2
```

2) component の存在確認（簡易）
```bash
python - << 'PY'
import pandas as pd, glob
p = sorted(glob.glob("runs/*/generate/data/particles.*"))[-1]
df = pd.read_parquet(p) if p.endswith(".parquet") else pd.read_csv(p)
assert "component" in df.columns, df.columns
# sample_id単位で component 種類数を確認
g = df.groupby("sample_id")["component"].nunique()
print(g.describe())
assert g.max() >= 2
PY
```

3) viz（可能なら）
```bash
python -m synthlab.cli.main process=viz input_run="runs/<run_name>/generate" seed=2
```

4) pytest
```bash
pytest -q
```

## Dependencies
- depends_on: [T0201]  # taxonomy_v2 と整合する前提で進める

## Implementation Notes
- DSLの解釈は composite generator 内に閉じる。各pattern generator を改造しない（肥大化防止）。
- transform は極座標系で実装し、境界（r<0, theta wrap）を必ずクリップ/正規化する。
- “粒子数配分” は `n_particles_total` を決めたうえで weight で割る設計が安定。
- config は将来のドメインにも転用できるよう、transform 名称は汎用寄りにする。

## DoD
- [ ] プリセット最低5つ
- [ ] 再現性テスト
- [ ] docs に composite DSL の書き方を examples または docs/ に追記
