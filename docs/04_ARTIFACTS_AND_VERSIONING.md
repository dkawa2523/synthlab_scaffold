# 04_ARTIFACTS_AND_VERSIONING — Artifact契約とバージョニング

## 1. Artifact（run）ディレクトリ契約（MUST）
各 Process の出力は **単一の run ディレクトリ**に保存される。
最低限、以下を持つ。

```
runs/<run_name>/<process.name>/
  config/
    resolved.yaml
    overrides.txt
  meta/
    meta.json
  data/                     # generate/export の主出力
  metrics/                  # qc/eval 等
  plots/                    # viz
  logs/
    console.log             # 可能なら
  README.md                 # そのrunの要約（自動生成可）
```

Hydraが自動生成する `.hydra/` は残っていても良いが、
**契約として参照するのは上記 config/** とする（将来の移植性のため）。

## 2. meta.json（MUST）
最低限フィールド（例）:
- `run_name`
- `process_name`
- `created_at`（ISO8601）
- `seed`
- `git_sha`（取得できるなら。取得不能なら null + TODO）
- `config_hash`（resolved.yaml の hash 先頭12桁など）
- `domain`
- `schema_version`
- `notes`（任意）

## 3. データ出力（wafer_particles v1）
### 3.1 particles（点群テーブル）
推奨: Parquet（学習/解析で扱いやすい）

必須列（v1）:
- `sample_id` : str（run 内でユニーク）
- `particle_id`: int（sample内でユニーク）
- `r_mm` : float
- `theta_rad` : float（0..2π）
- `size_um` : float（粒径）
- `label` : str（細粒度パターンラベル）
推奨列:
- `x_mm`, `y_mm`（派生。常に同一変換関数で生成）
- `component`（composite 生成時の成分ラベル）
- `source`（"synthetic" 等）

### 3.2 samples（サンプルメタ）
- `sample_id`
- `label`
- `n_particles`
- `pattern_params`（JSON文字列 or 列展開。P0はJSON文字列推奨）
- `seed_offset`（サンプル内seed派生に使った値）

### 3.3 manifest
- `manifest.json` または `manifest.yaml`
- データファイルの相対パス、行数、schema_version、label分布など

## 4. スキーマバージョン
- `schema_version` は `wafer_particles.v1` のように明示する
- 互換性破壊（列名変更/意味変更）は blocked運用
- 追加列は後方互換（基本OK）

## 5. バージョニング（比較可能性）
- 生成器の変更は config に必ず反映される（新しいrunを作る）
- `config_hash` と `git_sha` で追跡する
- datasetの “配布版” を作る場合は `export` process が `dataset_id` を確定させる

## 6. TODO
- `git_sha` が取得できない環境（zip配布等）の扱い: TODO
