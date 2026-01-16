# Artifacts & Versioning（runs/契約）

このドキュメントは、`runs/` 以下に出力される成果物の **契約**（何がどこに出るべきか）をまとめます。

> 原則: run成果物は immutable（後から書き換えない）。新しい実行は新しいrunに出す。

---

## 1. なぜ契約が必要か？

| 問題 | 契約がないと | 契約があると |
|---|---|---|
| 再現性 | いつ・どの設定で生成したか不明 | `resolved.yaml` で追跡 |
| 比較可能性 | 出力形式が揺れて比較不能 | 同じ構造で比較可能 |
| レビュー | 生成物の確認が困難 | どこを見ればよいか固定 |
| 配布 | 学習パイプラインが壊れやすい | exportが安定する |

---

## 2. 推奨 run 構造（概念）

```text
runs/<timestamp>_<process>/
  meta/
    resolved.yaml         # 合成後設定（真実）
    overrides.txt         # CLI override
    versions.json         # code/config hash 等（実装に依存）
    dataset_card.md       # export時（推奨）
  data/
    particles.(parquet|csv)
    samples.(parquet|csv)
  reports/
    qc_stats.json
    size_stats.csv
    coverage.json
  plots/
    wafer_scatter.png
    size_hist.png
```

> 実際のファイル名はプロジェクト実装を真実として、変更する場合は v2 を切って互換性を保ってください。

---

## 3. 必須メタ情報

| メタ | 必須度 | 理由 |
|---|---:|---|
| resolved config | MUST | 再現性の根幹 |
| seed | MUST | 決定論の根幹 |
| size_model / size_params | SHOULD | per_sample / mix を追跡 |
| labeling spec hash | SHOULD | label再編の比較性 |
| dataset version id | SHOULD | 配布・共有時の識別子 |

---

## 4. Export（配布）契約

### 4.1 split
- splitは **sample_id単位**（リーク禁止）
- ratio（8:1:1）や層化（stratify_by）を設定可能にする

### 4.2 dataset_card
データセットを配布するときは dataset card を生成します（推奨）。

含めたい項目:
- wafer条件（300mm等）
- パターン/分布の構成（比率）
- 粒子数レンジ
- 粒径レンジ・分布
- 生成日時・seed・config hash

---

## 5. 互換性のルール

| 変えるもの | 影響 | ルール |
|---|---|---|
| カラム名 | 下流ML/解析が壊れる | 破壊的変更は v2 を切る |
| 単位 | 学習が壊れる | 変更は禁止。どうしてもなら新カラム追加 |
| split方式 | 精度比較が崩れる | 変更するなら明示して dataset card に記録 |
