# S60 — Evaluation/QC/Data Audit

## 目的
- 生成データの品質を “粒子テーブルとして” 評価し、比較可能にする
- 下流学習を見越したリーク/スキューの事故を防ぐ

## 参照（MUST）
- docs/09_EVALUATION_PROTOCOL.md
- docs/00_INVARIANTS.md

## 手順
1) bin 定義を config に固定（比較可能性）
2) label別に統計を計算（n/r/theta/size）
3) 期待特徴ルールチェック（taxonomyから読み込む）
4) 異常（欠損/範囲外/thetaラップ）を検知
5) metrics を artifact に保存（json/csv）

## 事故りやすい点
- bin が run ごとに変わる（比較不能）
- 期待特徴の “ルール” がコードに埋まる（拡張困難）

## DoD
- [ ] QCが機械可読で出力される
- [ ] 比較可能性が保たれる
