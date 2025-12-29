# S50 — Artifact Contract & I/O

## 目的
- 出力形式を将来の学習・解析で扱いやすくし、比較可能性を担保する

## 参照（MUST）
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/00_INVARIANTS.md

## 手順
1) schema_version を固定し、必須列を確定
2) Parquet を第一候補にする（大規模生成に耐える）
3) manifest を出す（ファイル/行数/label分布/スキーマ）
4) meta.json に config_hash/seed 等を必ず入れる
5) 互換性破壊があるなら blocked運用

## 事故りやすい点
- 粒子列の意味変更（theta単位など）を無自覚に行う
- 変換関数が複数箇所に散る（skew）

## DoD
- [ ] schema validate が通る
- [ ] manifest と meta が揃う
- [ ] 同一runを他環境に移しても読める
