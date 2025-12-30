# 04_ARTIFACTS_AND_VERSIONING — Artifact契約とバージョニング（更新 v2.2）

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

---

## 2. meta.json（MUST）
最低限フィールド（例）:
- `run_name`
- `process_name`
- `created_at`（ISO8601）
- `seed`
- `git_sha`（取得できるなら。取得不能なら null + TODO）
- `config_hash`（resolved.yaml の canonical hash 先頭12桁）
- `domain`
- `schema_version`
- `notes`（任意）

---

## 3. config_hash の定義（重要・MUST）

### 3.1 目的
`config_hash` は **比較可能性** と **再現性** のための指紋です。
**実行ごとに変わる値（run_name、Hydraのruntime）に依存してはいけません。**
同一の「実質的な設定」であれば run_name が違っても `config_hash` は同一であるべきです。

### 3.2 canonicalization（MUST）
`config/resolved.yaml` から `config_hash` を計算する前に、次の処理を行います。

- ルートの `hydra` キーは除外（存在する場合）
- ルートの `run_name` は除外（存在する場合）
- それ以外のキーは保持（※将来必要なら ignore list は拡張可能。互換性注意）

### 3.3 ハッシュ計算（MUST）
- canonicalized config を **stable dump** する（key を sort する）
- SHA-256 を取り、先頭12桁を `config_hash` とする

擬似コード例:
```python
import yaml, hashlib, copy
cfg = yaml.safe_load(open("resolved.yaml"))
x = copy.deepcopy(cfg)
x.pop("hydra", None)
x.pop("run_name", None)
dumped = yaml.safe_dump(x, sort_keys=True)
config_hash = hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:12]
```

---

## 4. データ出力（wafer_particles v1）
### 4.1 particles（点群テーブル）
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

### 4.2 samples（サンプルメタ）
必須列:
- `sample_id` : str
- `label` : str
- `n_particles` : int
- `pattern_params` : str（JSON文字列 or 列展開。P0はJSON文字列推奨）
- `seed_offset` : int（サンプル内seed派生に使った値）

### 4.3 manifest
- `manifest.json` または `manifest.yaml`
- データファイルの相対パス、行数、schema_version、label分布など

---

## 5. スキーマバージョン
- `schema_version` は `wafer_particles.v1` のように明示する
- 互換性破壊（列名変更/意味変更）は blocked運用
- 追加列は後方互換（基本OK）

---

## 6. バージョニング（比較可能性）
- 生成器の変更は config に必ず反映される（新しいrunを作る）
- `config_hash` と `git_sha` で追跡する
- datasetの “配布版” を作る場合は `export` process が `dataset_id` を確定させる

---

## 7. TODO
- `git_sha` が取得できない環境（zip配布等）の扱い: TODO
