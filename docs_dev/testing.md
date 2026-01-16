# Testing & Quality Gates

このドキュメントは、品質ゲート（doctor/qc/tests）とテスト作法をまとめます。

---

## 1. 何を守りたいか（品質目標）

| 品質目標 | 具体的な検証 |
|---|---|
| 再現性 | seed固定で同一出力 |
| wafer内制約 | rが半径を超えない |
| スキーマ安定 | columns/unitsが揺れない |
| 分布妥当性 | clamp、パラメータ範囲 |
| 互換性 | 既存ベンチが壊れない |

---

## 2. 品質ゲート

### 2.1 doctor（実行前）
- 設定ミスで “壊れた生成” を止める
- 未定義dist、範囲逆転、単位桁ミス、比率不正など

### 2.2 qc（実行後）
- 統計/特徴量（size_stats 等）で “生成結果が想定内か” を見る
- heavy-tail の暴走や粒子数の偏りを検知

### 2.3 pytest（変更時）
- 新規パターン/分布は必ずテストを追加
- 回帰を防ぐ

---

## 3. 推奨テスト構成

| テスト | 目的 | 例（ファイル名は任意） |
|---|---|---|
| schema test | columns/型 | `test_schema.py` |
| determinism test | seedで一致 | `test_reproducibility.py` |
| patterns smoke | 全pattern生成 | `test_patterns_smoke.py` |
| size models | clamp/重尾 | `test_size_models.py` |
| selection mix | 比率・記録 | `test_size_model_selection.py` |
| export | split整合 | `test_export.py` |

---

## 4. スモークテスト運用（推奨）

`conf/benchmarks/wafer_particles/*_smoke.yaml` を必ず用意し、以下をPASS条件にする:

- doctor PASS
- generate（20サンプル程度）PASS
- qc PASS
- export PASS

---

## 5. ありがちな失敗と対策

| 失敗 | 原因 | 対策 |
|---|---|---|
| seedが未指定 | 再現性が崩れる | doctorで必須化 |
| sizeが範囲外 | clamp不足 | 全モデル共通のclampを通す |
| export split が粒子単位 | リーク | sample_id 単位を固定 |
| θの定義域が混在 | sin/cos変換で問題 | schemaで定義域を固定、テストを書く |
