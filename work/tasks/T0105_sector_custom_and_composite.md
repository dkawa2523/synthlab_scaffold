# TASK: T0105 パターン生成バリエーション拡張（任意角度セクタ/リング＋ホットスポット合成）(P1)

## Contracts
- docs/11_PLUGIN_REGISTRY.md
- docs/00_INVARIANTS.md
- docs/09_EVALUATION_PROTOCOL.md

## Summary
セクタ（edge_sector）の **任意角度中心**対応と、`composite` を使った **リング＋ホットスポット**の代表例を追加する。

## Scope
- `edge_sector` に `mode: custom`（または `side: custom`）を追加し、`angle_center_rad` を受け取れるようにする
- `composite` の例を `conf/wafer_particles/patterns/` に追加（ring + hotspot）
- 生成結果に `component` 列がある場合、両成分が識別できるようにする

## Acceptance Criteria
- [ ] `pytest -q tests/test_T0105_sector_custom_and_composite.py` が通る
- [ ] custom angle の sector で、theta が指定中心近傍に偏ることが統計的に確認できる（テスト内で簡易チェック）
- [ ] composite（ring+hotspot）で、2成分が生成されていることが確認できる（component列 or 2つのクラスタ特性）

## Implementation Notes
- 既存の taxonomy/label を増やさず、同じ label でパラメータ差分として扱ってよい
- 再現性（seed）と入出力（artifact契約）を壊さない

## Verification
- `pytest -q tests/test_T0105_sector_custom_and_composite.py`
