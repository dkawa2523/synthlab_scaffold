# S40 — Process Implementation & CLI

## 目的
- generate/qc/viz/export/train/eval 等の Process を “同じ型” で実装し、比較可能にする

## 参照（MUST）
- docs/10_PROCESS_CATALOG.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/00_INVARIANTS.md

## 手順
1) Process の I/O を決める（入力artifact/出力artifact）
2) 解析/生成の “純度” を守る（run dir 外に出さない）
3) artifact writer を使って config/meta を必ず保存
4) 成果物（data/metrics/plots）を契約通り配置
5) 失敗時にログが残るようにする（最低限 console.log）

## 事故りやすい点
- Process が別Processの内部実装を import して依存する
- 例外時に途中ファイルだけ残る（manifest不整合）

## DoD
- [ ] artifact 契約を満たす
- [ ] 同一設定で再実行可能
- [ ] 入出力が docs/10 の記述と一致
