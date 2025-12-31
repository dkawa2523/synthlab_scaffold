# TASK: T0106 複雑な物理ノイズの導入（位置ジッタ・バックグラウンドノイズ）(P1)

## Contracts
- docs/00_INVARIANTS.md
- docs/11_PLUGIN_REGISTRY.md
- docs/09_EVALUATION_PROTOCOL.md

## Summary
理想パターンに対して、装置起因の「にじみ」を模擬するための **位置ジッタ** と **背景ノイズ**を追加する。

## Scope
- `process=generate` の共通後処理として以下を追加（全パターンに適用可能）
  - 位置ジッタ：r/theta に小さなガウスノイズ（stdをconfig化）
  - 背景ノイズ：一様ランダム粒子を追加（countまたはfractionで指定）
- config で ON/OFF 可能にする（デフォルトOFF）

## Acceptance Criteria
- [ ] `pytest -q tests/test_T0106_noise_jitter_and_background.py` が通る
- [ ] jitter ON で r/theta の分散が増えることが確認できる
- [ ] background ON で粒子数が増えることが確認できる
- [ ] seed固定で再現する

## Implementation Notes
- theta は 0..2π に正規化、r は 0..R へクリップ等の安全策を必ず入れる

## Verification
- `pytest -q tests/test_T0106_noise_jitter_and_background.py`
