# TASK: T0205 データセット配布用 export 強化（dataset bundle / checksums / card）(P0)

## Summary
- export artifact を “配布可能な dataset bundle” として整形し、学習や共有に使いやすくする。
- dataset_id、manifest、checksums、dataset card を出力し、後から再利用・比較できるようにする。

## Contracts (MUST READ)
- docs/04_ARTIFACTS_AND_VERSIONING.md（artifact契約/バージョニング）
- docs/03_CONFIG_CONVENTIONS.md（Hydra）
- docs/00_INVARIANTS.md（immutability/比較可能性）
- docs/05_SECURITY_SECRETS.md（実測を含む場合の注意）

## Scope
- `process=export` を拡張し、以下の “bundle” を生成
  - `data/`（particles/samples）
  - `splits/`（train/val/test の sample_id リスト）
  - `manifest.yaml/json`（label統計、schema_version、taxonomyバージョン、config_hash）
  - `checksums.sha256`（bundle内の全ファイル）
  - `DATASET_CARD.md`（概要、スキーマ、taxonomy、生成条件の要約）
  - `taxonomy_snapshot.yaml`（使用したtaxonomyをスナップショット）
- bundle を1ファイルに固めるオプション（任意）
  - `export.package.format: none|zip|tar.gz`
  - 出力例: `data/dataset_<dataset_id>.zip`
- dataset_id を安定化（MUST）
  - `dataset_id = f"{schema_version}_{taxonomy_version}_{config_hash[:12]}"` など
  - **run_nameなどの実行時値は含めない**
- 既存の export 出力との後方互換を維持（既存ファイルは残しても良い）

## Non-goals
- DVC/外部レジストリ連携（docs/12）
- HF datasets へのアップロード自動化

## Inputs / Outputs
- Inputs:
  - generate artifact
- Outputs:
  - export artifact（bundle一式）
  - tests（dataset_id安定、checksums生成）

## Acceptance Criteria (MUST)
- [ ] export 実行で bundle が生成される（manifest、checksums、card、taxonomy_snapshot）
- [ ] `export.package.format=zip` のとき zip が生成される
- [ ] 同一config+seedで2回 export しても dataset_id が一致する（小規模でOK）
- [ ] checksums が bundle 内ファイルと一致する（検証関数/スクリプトでOK）

## Verification (MUST)
1) 生成→export（package=zip）
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=20 seed=20
python -m synthlab.cli.main process=export input_run="runs/<run_name>/generate" export.package.format=zip seed=20
```

2) dataset_id の安定性（同一設定で再実行して一致）
```bash
python -m synthlab.cli.main process=export input_run="runs/<run_name>/generate" export.package.format=zip seed=20
python - << 'PY'
import glob, yaml, os
mans = sorted(glob.glob("runs/*/export/data/manifest.*"))
m1 = mans[-1]
m = yaml.safe_load(open(m1)) if m1.endswith(".yaml") else None
assert m is not None and "dataset_id" in m
print("dataset_id:", m["dataset_id"])
PY
```

3) checksums が存在
```bash
ls runs/*/export/data/checksums.sha256
```

4) pytest
```bash
pytest -q
```

## Dependencies
- depends_on: [T0201, T0102]  # taxonomy_v2 + 既存exportの上に拡張

## Implementation Notes
- checksums は `sha256(file_bytes)` を行単位で保存（`<hash>  <relative_path>`）
- DATASET_CARD.md はテンプレでよい（schema、列、ラベル一覧、作成日時、config_hash）
- 互換性: 既存の `data/particles.parquet` 等は残しつつ、bundle関連ファイルを追加する方向が安全
- zip/tar は Python標準ライブラリで実装可

## DoD
- [ ] bundleファイル一式
- [ ] dataset_idの安定性テスト
- [ ] docs/04 に export bundle 追記（軽くでOK）
