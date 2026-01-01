# 10_PROCESS_CATALOG — Process一覧とI/O

## 共通事項（MUST）
- すべての Process は Hydra config で選択される
- すべての Process は artifact 契約（docs/04）を満たす
- 入力が artifact の場合、参照はパス + meta を読み取り、再現可能な形にする

---

## P0で実装するProcess
### 1) process=generate
目的: 擬似粒子データ（wafer_particles）を生成し、data/ に保存  
入力: Hydra config のみ  
出力:
- data/particles.parquet(or csv)
- data/samples.parquet(or csv)
- manifest
- metrics/（最低限の集計）
- plots/（任意、最小でもOK）

### 2) process=compose
目的: 既存サンプルを合成し multi-label な複合サンプルを生成  
入力:
- generate/export の artifact（または data/ パス）
出力:
- data/particles.parquet(or csv)
- data/samples.parquet(or csv)
- compose_manifest.json
- manifest
- metrics/compose_summary.json
- metrics/（最低限の集計）
- plots/（任意、最小でもOK）

### 3) process=qc
目的: 生成データの統計/QCを計算し metrics/ に保存  
入力:
- generate の artifact（または data/ パス）
出力:
- metrics/qc.json
- metrics/label_summary.csv
- plots/（任意）

### 4) process=audit
目的: 生成/配布データの欠損/範囲外/重複/リークを検知しレポートする  
入力:
- generate/export の artifact（または data/ パス）
出力:
- metrics/audit.json
- metrics/audit_tables/*.csv（任意）

### 5) process=viz
目的: 可視化（ラベル別サンプル、ヒストグラム、密度など）  
入力:
- generate の artifact（または data/ パス）
出力:
- plots/*.png（またはhtml）
- metrics/（必要なら）

### 6) process=doctor
目的: 環境・依存・設定の健全性チェック（壊れやすい点を事前検知）  
入力: なし  
出力:
- meta/doctor.json（OK/NG、バージョン、GPU有無など）

### 7) process=compare
目的: run A/B の粒子テーブル距離を計算し比較レポートを残す  
入力:
- generate/export の artifact（run_dir）x2
出力:
- metrics/compare_summary.json
- metrics/compare_table.csv
- plots/compare_*.png（任意）

### 8) process=pattern_coverage
目的: 実測/疑似実測に対して既存パターンの被覆度を評価し、必要なら新パターン/複合を提案  
入力:
- 実測データ（artifact or data path）
- pattern_set（対象パターン）
- search_budget（各パターンの候補数）
出力:
- reports/coverage_summary.json
- reports/coverage_summary.md
- metrics/coverage_summary.json
- plots/coverage_*.png（任意）

---

## P1以降で実装予定（契約だけ先に固定）
### 9) process=fit_params
目的: 実測/疑似実測データからパターン主要パラメータを推定  
入力:
- particles/samples の artifact（または data/ パス）
出力:
- metrics/estimated_params.json（label別/推定パラメータ+統計）

### 10) process=calibrate_search
目的: 実測/疑似実測の分布距離を最小化するパラメータ探索  
入力:
- real dataset（artifact or data path）
- search space（YAML: param ranges / n_trials / seed）
出力:
- metrics/best_score.json
- metrics/trials.csv
- config/best_config.yaml

### 11) process=export
目的: 学習で使いやすい形にパッケージ（split、index、dataset_id）  
入力: generate artifact  
出力: export artifact（data/ + splits + manifest）

### 12) process=labeling_apply
目的: 外部ラベリング spec を適用して派生ラベル層を付与  
入力:
- export artifact（run_dir）
- labeling spec（YAML path）
出力:
- data/particles.* + data/samples.*（派生ラベル列追加）
- labels_<layer> は JSON string array として保存（CSV/Parquet共通）
- meta/labeling_spec.yaml + meta/labeling_spec_hash.txt
- reports/labeling_layers_summary.json
- reports/similarity_groups_summary.json
- metrics/labeling_apply_summary.json

### 13) process=train / eval / predict
目的: 下流学習（分類/検知/回帰）を統一インターフェースで扱う  
入力: export artifact + model config  
出力: model/ + metrics/ + preds/

### 14) process=leaderboard
目的: runs を集計して比較表を生成  
入力: runs/ の複数artifact  
出力: leaderboard.csv / html

### 15) process=size_qc
目的: 粒径分布のQC/特徴量抽出（異常検出・学習用の統計量）  
入力:
- generate の artifact（または data/ パス）
出力:
- reports/size_stats.csv
- reports/size_model_mix.json
- metrics/size_qc_summary.json
- plots/（任意、最小でもOK）

※ 具体仕様は work/tasks で作る（TODO）
