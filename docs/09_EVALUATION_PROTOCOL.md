# 09_EVALUATION_PROTOCOL — 評価プロトコル（QC/比較ルール）

## 1. 目的
- 擬似データが「意図したラベル/パターン」を満たすか
- 擬似データが「学習データとして扱いやすい品質」を持つか
- run間比較（改善の効果測定）を正しく行う

## 2. 原則（MUST）
- 同一 seed 方針・同一 bin 定義・同一 metric 定義で比較する
- 評価コード/設定も artifact に保存する（docs/04）
- “見た目だけ良い” を禁止：必ず粒子テーブルで評価する（docs/00）

## 3. QC（生成品質）メトリクス（wafer_particles v1）
### 3.1 分布系（必須）
- 粒子数 `n_particles` の分布（label別）
- 半径方向ヒストグラム `hist_r`（同一bin）
- 角度方向ヒストグラム `hist_theta`（同一bin）
- 粒径分布（平均、分散、分位点、KS距離の計算準備）

### 3.2 空間構造（推奨）
- 最近傍距離分布（NN distance）
- ペア相関（近距離でのクラスタ/反発の指標）
- 簡易 Ripley’s K/L（P1で導入可）

### 3.3 ラベル整合性（必須）
- label別に「期待特徴」が満たされるか（ルールチェック）
  - ring系: rの分散が閾値内、thetaが広く分布
  - sector系: thetaが狭い範囲に集中
  - scratch/radial: 直線フィット残差が小さい（簡易でOK）
  - hotspot: 密度中心が存在し、外側で密度減衰

※ “期待特徴” のルールは taxonomy_v1 / taxonomy_v2 と一緒に管理（Hydra YAML）

## 4. 実測との比較（任意・推奨）
- 実測が少ない場合でも、同一指標で距離を計算し目安にする
- 実測データ取り込みはセキュリティ規定に従う（docs/05）
- TODO: 実測比較の正式手順（データ共有方法）

## 5. 下流学習での評価（将来）
- synthetic で学習 → real でテスト（リーク防止）
- 同一 split/seed を守る
- metric（F1/PR-AUC/混同行列）を artifact に保存
- TODO: 学習パイプラインの具体仕様（P1）

## 6. 比較ルール（MUST）
- run A と run B の比較は
  - 同一 schema_version
  - 同一 evaluation config（bin等）
  - 同一 seed 方針
  - 同一 dataset_id（比較目的が generator のみの場合は dataset_id を固定するなど）
  を満たすこと

## 7. TODO
- “良い擬似データ” の合格基準（閾値・許容範囲）: TODO（実測/運用で決める）
