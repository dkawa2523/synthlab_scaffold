# TASK: T0101 点過程モデル拡張（P1）

## Contracts
- docs/11_PLUGIN_REGISTRY.md
- docs/09_EVALUATION_PROTOCOL.md

## Scope
- 非一様Poisson（lambda(r,theta)）
- クラスタ過程（親点→子点）
- Cox（ランダム強度場）※重い場合は後回し可
- 既存 taxonomy に追加し、期待特徴ルールも追加

## Acceptance Criteria
- [ ] 既存の generate/qc/viz にそのまま刺さる（plugin）
- [ ] QCメトリクスで違いが確認できる
