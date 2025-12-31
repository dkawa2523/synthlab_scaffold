# Future Backlog (提案) — Phase 3+

このファイルは **今すぐ queue に入れない**が、将来の拡張候補を整理したバックログです。
ID は提案です（必要になったら work/queue.json に起票してください）。

---

## T0300: 生成スケール/品質の強化（運用P0候補）
- **T0301** 大規模生成の性能最適化
  - streaming parquet writer / chunk生成 / メモリ上限 / 並列生成（multiprocessing）
- **T0302** ラベル分布制御の高度化
  - labelごとの粒子数分布・混合比・パラメータ範囲を YAML で管理
- **T0303** データ監査（Data Audit）強化
  - 重複検出、漏洩チェック、外れ値・欠損の自動レポート（docs/09 に整合）

## T0400: 実測少数データでのキャリブレーション（価値大）
- **T0401** 実測→パラメータ推定（簡易フィット）
  - 例: ringの平均半径/幅、sector角度幅、edge bias 係数などを推定し synthetic に反映
- **T0402** synthetic-to-real の距離最小化ループ
  - compare の距離を目的関数にして generator のハイパラを探索（Bayes/ランダム）
- **T0403** 実測の匿名化/アクセス制御運用（docs/05補強）

## T0500: 高度な生成モデル（深層学習 / diffusion / VAE / flow）
- **T0501** 画像化（density map）→ diffusion / UNet で生成 → 点群サンプリング
- **T0502** 点群直接生成（PointFlow/Score-based/Transformer）
- **T0503** 条件付き生成（coarse/fine label 条件、装置条件条件など）
- **T0504** 少数実測でのファインチューニング戦略（LoRA等）※要調査

## T0600: 学習パイプラインの本格化（MLOps手前）
- **T0601** モデル比較（leaderboard）強化
  - seed固定、CV、スコア統一、レポートHTML
- **T0602** FeaturePipeline 統一（skew排除の強化）
- **T0603** ハイパラ探索（Hydra multirun）と結果集計

## T0700: 可視化/UX（開発効率UP）
- **T0701** 生成/QC/compare をまとめた “HTMLレポート” 出力
- **T0702** Streamlit などの簡易UI（ローカル）※P2
- **T0703** 2D/3D インタラクティブプロット（plotly）

## T0800: データセット管理/配布
- **T0801** dataset registry（dataset_id の一覧化、メタDB化）
- **T0802** HF datasets 互換出力（ローカルのみ）
- **T0803** 外部ストレージ（S3等）への同期（docs/12 を満たしてから）

## T0900: セキュリティ/運用
- **T0901** 実測データ取り扱い手順の確定（社内規定反映）
- **T0902** CI 導入（pytest、lint、typecheck）
- **T0903** Docker/再現環境（ローカル/CI）
