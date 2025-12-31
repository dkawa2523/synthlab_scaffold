# TASK: T0402 距離最小化による自動キャリブレーション（パラメータ探索ループ）(P1)

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/09_EVALUATION_PROTOCOL.md
- docs/10_PROCESS_CATALOG.md

## Summary
実測（少数）に対して、生成器パラメータを自動探索し、**分布距離（hist/size/空間統計）**を最小化するキャリブレーションループを導入する。

## Scope
- 新規 Process（例）：`process=calibrate_search`
  - input: real dataset（または proxy real）
  - input: search space（YAML）: パターン/パラメータの探索範囲、試行回数、seed、評価指標
  - output:
    - `metrics/best_score.json`
    - `metrics/trials.csv`（各試行のパラメータとスコア）
    - `config/best_config.yaml`（推奨生成設定）
- 探索アルゴリズム（P1で十分）
  - ランダムサーチ or Latin Hypercube など、依存ライブラリ無しで実装可能なもの
- 評価距離
  - 最低限: r/theta/size のヒスト距離（L1/JS/KL 等のうち実装容易なもの）
  - 可能なら: 最近傍距離分布の距離なども追加（オプション）

## Non-goals
- ベイズ最適化（依存追加が必要ならP2）
- 本格的な物理シミュレーション統合

## Acceptance Criteria
- [ ] `process=calibrate_search` が実行でき、探索ログ（trials）と best_config を artifact に残す
- [ ] テスト用の proxy real（既知パラメータの合成）に対し、探索で距離が明確に改善する（初期点より best が良い）
- [ ] seed固定で探索結果が再現できる（docs/00）

## Verification
- `pytest -q -k T0402`

## Implementation Notes
- T0401 の推定値を初期値として探索を開始しても良い（warm start）
- “real” の取り扱いは docs/05 を守る。テストでは合成データで代替する
