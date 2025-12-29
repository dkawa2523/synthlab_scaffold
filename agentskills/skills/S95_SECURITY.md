# S95 — Security/Secrets/Compliance

## 目的
- 秘密情報や実測データの漏洩事故を防ぎつつ開発を進める

## 参照（MUST）
- docs/05_SECURITY_SECRETS.md
- docs/00_INVARIANTS.md

## 手順
1) 追加する設定に秘密が含まれないか確認
2) 必要なら env 経由にする
3) 実測データを扱うなら保存場所/権限/匿名化を TODO として明示
4) 生成artifactに機密が混入していないか確認

## DoD
- [ ] secrets が repo に入らない
- [ ] 実測データ導入は TODO/手順化されている
