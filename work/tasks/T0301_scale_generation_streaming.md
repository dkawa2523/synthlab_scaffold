# TASK: T0301 生成スケール最適化（ストリーミング書き出し/チャンク生成）(P0)

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/10_PROCESS_CATALOG.md
- docs/11_PLUGIN_REGISTRY.md

## Summary
大量生成（数万〜数十万サンプル）でもメモリ爆発せずに回るよう、`process=generate` を **チャンク生成 + ストリーミング書き出し**対応にする。

## Scope
- `process=generate` の実装を「全件を一度にDataFrame化」から脱却し、以下のどちらか（または両方）を実装する：
  1) **チャンク生成**: `chunk_size`（例: 100〜1000 sample/chunk）単位で生成し、逐次 `data/` に追記
  2) **ストリーミング書き出し**: ParquetWriter等を用いて `particles`/`samples` を追記（行数が大きくても安定）
- Hydra config で以下を追加（命名は docs/03 に従い、後方互換を保つ）
  - `wafer_particles.generate.chunk_size: int`
  - `wafer_particles.io.write_mode: [eager|streaming]`（デフォルト eager = 従来挙動）
  - （任意）`wafer_particles.io.compression: zstd/snappy/...`
- manifest 生成もチャンク対応（最終行数・ラベル分布・schema_version は正しく出力）
- 再現性:
  - 同一 seed + 同一 config で、生成結果（少なくとも manifest の集計）が一致すること（docs/00）

## Non-goals
- 分散実行（Ray/Spark等）導入
- GPU最適化
- Parquetの高度なパーティション設計（必要なら後続タスクで）

## Acceptance Criteria (MUST)
- [ ] `write_mode=streaming` で `n_samples=10_000` 程度の生成が **メモリ過大消費せず**完走する（ローカルPC想定）
- [ ] `data/particles.*` と `data/samples.*` が生成され、行数が `manifest` と整合する
- [ ] 既存の `write_mode=eager`（もしくは未指定）で従来どおり動く（後方互換）
- [ ] seed固定で 2回実行しても、（最低限）`label_summary`/`manifest` の主要集計が一致する

## Verification (MUST)
- `pytest -q -k T0301`

## Implementation Notes
- 可能なら Parquet を第一候補（docs/04）。ただし pyarrow が無い環境も想定し、CSV fallback を用意して良い
- ストリーミング時も `meta/config` は run 開始時に固定保存する（docs/04）
- RNG は必ず注入し、チャンク境界で再現性が壊れないようにする（docs/00）
