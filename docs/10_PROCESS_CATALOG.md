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

### 2) process=qc
目的: 生成データの統計/QCを計算し metrics/ に保存  
入力:
- generate の artifact（または data/ パス）
出力:
- metrics/qc.json
- metrics/label_summary.csv
- plots/（任意）

### 3) process=viz
目的: 可視化（ラベル別サンプル、ヒストグラム、密度など）  
入力:
- generate の artifact（または data/ パス）
出力:
- plots/*.png（またはhtml）
- metrics/（必要なら）

### 4) process=doctor
目的: 環境・依存・設定の健全性チェック（壊れやすい点を事前検知）  
入力: なし  
出力:
- meta/doctor.json（OK/NG、バージョン、GPU有無など）

---

## P1以降で実装予定（契約だけ先に固定）
### 5) process=export
目的: 学習で使いやすい形にパッケージ（split、index、dataset_id）  
入力: generate artifact  
出力: export artifact（data/ + splits + manifest）

### 6) process=train / eval / predict
目的: 下流学習（分類/検知/回帰）を統一インターフェースで扱う  
入力: export artifact + model config  
出力: model/ + metrics/ + preds/

### 7) process=leaderboard
目的: runs を集計して比較表を生成  
入力: runs/ の複数artifact  
出力: leaderboard.csv / html

※ 具体仕様は work/tasks で作る（TODO）
