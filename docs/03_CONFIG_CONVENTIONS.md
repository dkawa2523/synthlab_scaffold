# 03_CONFIG_CONVENTIONS — Hydra（YAML）運用規約

## 1. 原則
- **すべて YAML**（Hydra）
- defaults リストで「構成」を表す
- すべての run は resolved config を artifact に保存（docs/04）
- seed は root に 1つ（docs/00）

## 2. conf/ 構造（推奨）
```
conf/
  config.yaml               # root（defaults）
  domain/
    wafer_particles.yaml
  process/
    generate.yaml
    qc.yaml
    viz.yaml
    export.yaml
    doctor.yaml
  wafer_particles/
    labels/
      taxonomy_v1.yaml
    patterns/
      ring_narrow.yaml
      ring_wide.yaml
      edge_sector.yaml
      scratch.yaml
      radial_lines.yaml
      hotspot.yaml
      random_uniform.yaml
      random_edge_biased.yaml
      composite.yaml
    size_models/
      lognormal.yaml
      gaussian.yaml
      mixture.yaml
    qc/
      default.yaml
    viz/
      default.yaml
    io/
      parquet.yaml
      csv.yaml
```

## 3. root config の基本形（例）
- `conf/config.yaml` の `defaults` で domain/process を必ず指定する
- process は dispatcher が選ぶ（同一 entrypoint で切り替える想定）

例:
```yaml
defaults:
  - domain: wafer_particles
  - process: generate
  - override hydra/job_logging: disabled
  - override hydra/hydra_logging: disabled

seed: 1234
run_name: ${now:%Y-%m-%d_%H-%M-%S}

hydra:
  run:
    dir: runs/${run_name}/${process.name}
  sweep:
    dir: sweeps/${run_name}
    subdir: ${hydra.job.num}
```

## 4. override の規約
- CLI からの override は meta に残す（artifactに保存）
- “同名キーの意味変更” は禁止（互換性崩壊なので blocked運用）

例:
- `python -m synthlab.cli.main process=generate wafer_particles/patterns=ring_narrow seed=42`

## 5. seed の規約
- root `seed` を唯一の seed とし、派生 seed は `seed + hash(component)` で作る（実装側で統一）
- seed 未指定は禁止（必ず入れる）

## 6. スキーマ検証（推奨）
- OmegaConf の structured config（dataclass）または pydantic を検討
- “型安全”導入は段階的に（P0: 最低限の必須キー存在チェック）
- 詳細は work/tasks で実装

## 7. TODO
- hydra multirun での sweep ベストプラクティス（GPU/並列制御）: TODO
