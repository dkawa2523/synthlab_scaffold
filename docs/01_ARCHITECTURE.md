# 01_ARCHITECTURE — 構成と依存方向

## 1. 目的
- **拡張しても肥大化しない**構造（pattern/metric/viz/process が増えても一定の秩序）
- **複数ドメイン**（点群/画像/動画/時系列）へ拡張可能
- **Hydra設定**と **artifact契約**で、再現性・比較可能性を担保

## 2. 現状→理想（方針）
現状: wafer_particles を最初の Domain として実装開始  
理想: Domain を増やしても framework は共通、Domain固有は domains/ 配下に閉じる

## 3. 依存方向（重要）
下位層は上位層を import しない（逆依存禁止）。

```
[CLI / main]
    |
    v
[Process Dispatcher] -----> [Artifact I/O]
    |
    v
[Domain API] --------------> [Registry]
    |
    v
[Plugin Implementations] --> [Core Utils (rng, geometry, types)]
```

### 依存ルール
- Process は Domain API と Artifact I/O に依存してよい
- Domain API は core utils と registry に依存してよい
- Plugin 実装は Domain API（interface）と core utils に依存してよい
- core utils は他層に依存してはいけない
- Hydra/OmegaConf は “Process/CLI 層” に閉じる（Domain/Plugin が Hydra に依存しない）

## 4. 推奨ディレクトリ（骨格）
（実装は work/tasks で段階的に行う）

```
conf/                      # Hydra YAML
src/synthlab/
  cli/                     # entrypoint（Hydra main）
  framework/
    process.py              # process dispatch, base classes
    artifacts.py            # artifact contract & writer/reader
    registry.py             # plugin registry
  domains/
    wafer_particles/
      schema.py             # data schema / domain config
      generators/           # pattern + size models
      metrics/              # QC metrics
      viz/                  # plots
tests/
runs/                      # outputs（git管理しない）
```

## 5. 拡張戦略（肥大化防止）
### 5.1 新しいパターンを追加する
- `domains/wafer_particles/generators/patterns/` に実装を追加
- `docs/11_PLUGIN_REGISTRY.md` の登録規約に従って registry に登録
- Hydra config に pattern を追加（conf/ の group）

### 5.2 新しい Domain を追加する（将来）
- `src/synthlab/domains/<new_domain>/` を作り、同様の構造で閉じる
- framework 側は process/artifact/registry の共通I/Fを維持

## 6. 非目標（今はやらない）
- 特定のMLOps製品の強制（MLflow/ClearML/W&B等）：docs/12にチェックリストだけ用意
- 大規模分散処理：必要になったら blocked運用で導入
