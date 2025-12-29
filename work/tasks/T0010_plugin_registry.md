# TASK: T0010 Plugin Registry 実装とテスト

## Contracts
- docs/11_PLUGIN_REGISTRY.md
- docs/00_INVARIANTS.md

## Scope
- registry（register/get/list）を framework に実装
- namespaced key を強制
- 重複登録の防止/警告
- 最小テスト（登録→取得→呼び出し）

## Acceptance Criteria
- [ ] plugin を名前で解決できる
- [ ] 実装が巨大 if/else を不要にする

## Verification
- パターン/サイズ/メトリクスの登録をスモーク
