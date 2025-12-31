# TASK: T0201 Taxonomy階層化 v2（fine/coarse）と後方互換（P0）

## Summary
- 既存のラベル（fine粒度）を維持しつつ、**階層（coarse/fine）** と **メタ情報** を持つ `taxonomy_v2.yaml` を追加する。
- generate/qc/viz/export/train で「fineラベルは従来通り label 列」「coarseラベルは追加列 label_coarse」で扱えるようにする。

## Contracts (MUST READ)
- docs/00_INVARIANTS.md（skew禁止、再現性）
- docs/03_CONFIG_CONVENTIONS.md（Hydra group/override）
- docs/04_ARTIFACTS_AND_VERSIONING.md（samples/particlesスキーマ）
- docs/09_EVALUATION_PROTOCOL.md（期待特徴ルールの位置づけ）

## Scope
- `conf/wafer_particles/labels/taxonomy_v2.yaml` を新規追加
  - v1のラベルを包含（**ラベル名の変更/削除は禁止**）
  - 追加情報: `coarse`, `family`, `description`, `expected_rules`（文章）など
  - 生成器との対応: `generator`（pattern key 参照）を持てる形（必須ではないが推奨）
- Hydraで taxonomy を切替可能にする（例: `wafer_particles/labels=taxonomy_v2`）
- `samples` テーブルに後方互換な追加列を導入（**列追加はOK**）
  - `label`（= fine）: 既存のまま維持
  - `label_coarse`（新規）: taxonomy_v2 の coarse を書き込む
  - `label_family`（任意）: familyがあれば書き込む
- QC/Viz/Export/Train で `label_coarse` を利用できるようにする（最低限、読み込み・保存できる）
- docs に taxonomy_v2 の概要を追記（docs/04 または docs/09 に軽く追記。契約破壊は禁止）

## Non-goals
- 既存スキーマの破壊的変更（列名変更、意味変更、必須化）
- v1の削除
- “coarseでしか学習できない” などの限定（fine/coarse両対応）

## Inputs / Outputs
- Inputs:
  - conf/wafer_particles/labels/taxonomy_v1.yaml（参照）
- Outputs:
  - conf/wafer_particles/labels/taxonomy_v2.yaml
  - conf group 追加/更新（defaultsの追加は慎重に）
  - samplesテーブル: `label_coarse` 追加（parquet/csv出力に反映）
  - tests: taxonomy_v2を使ったgenerate→exportが通る

## Acceptance Criteria (MUST)
- [ ] `taxonomy_v2.yaml` が追加され、Hydra override で選択できる
- [ ] `process=generate` を taxonomy_v2 で実行してもエラーにならない
- [ ] 出力 `data/samples.*` に `label_coarse` 列が存在し、`label` と整合している
- [ ] `process=export` で出力される samples にも `label_coarse` が含まれる
- [ ] 後方互換: taxonomy_v1 を使っても従来通り動作する

## Verification (MUST)
以下を repo ルートで実行し、すべて成功すること。

1) small generate（taxonomy_v2）
```bash
python -m synthlab.cli.main process=generate wafer_particles.n_samples=20 wafer_particles/labels=taxonomy_v2 seed=1
```

2) export（直前の generate run を入力。examples の方式に従う）
```bash
python -m synthlab.cli.main process=export input_run="runs/<run_name>/generate" seed=1
```

3) samplesに列があることを確認（簡易）
```bash
python - << 'PY'
import pandas as pd, glob, os
p = glob.glob("runs/*/generate/data/samples.*")
print("samples:", p[-1])
df = pd.read_parquet(p[-1]) if p[-1].endswith(".parquet") else pd.read_csv(p[-1])
assert "label" in df.columns
assert "label_coarse" in df.columns
print(df[["label","label_coarse"]].head())
PY
```

4) pytest（存在する場合）
```bash
pytest -q
```

## Dependencies
- depends_on: [T0102]  # export がある前提（完了済みならそのまま進む）

## Implementation Notes
- taxonomy_v2 の設計は “ラベル辞書” として軽量に保つ。巨大な説明文は docs/ に寄せる。
- `label_coarse` の付与は、生成時（samples作成時）に taxonomy を参照して行う。
  - 既存コードで label が決まる地点を探し、そこで taxonomy lookup を行うのが安全。
- taxonomy_v1 と v2 の読み込みI/Fを統一し、実装側の if/else を増やさない（docs/11方針）。
- config_hash には run_name 等の実行時値を混ぜない（T0003で確立済みの方針を遵守）。

## Definition of Done (DoD)
- [ ] tests 追加（taxonomy v2 が読み込める・列追加が出る）
- [ ] docs 追記（1〜2段落でOK）
