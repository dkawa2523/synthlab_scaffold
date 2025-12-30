# TASK: T0003 Artifact契約（run dir / meta / config snapshot / manifest）の実装（更新 v2.2）

## Contracts (MUST READ)
- docs/00_INVARIANTS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## Summary
- ArtifactWriter/Reader 相当の共通ユーティリティを実装し、すべてのProcessが同じ契約で出力できるようにする。
- 特に `config_hash` は run_name などの実行時変数に依存しないように定義する（docs/04参照）。

## Scope
- `ArtifactWriter/Reader` 的なユーティリティ（framework）を作成
- `config/resolved.yaml` / `config/overrides.txt` / `meta/meta.json` を必ず保存
- `config_hash` を算出して meta に入れる（docs/04 の canonicalization を必ず守る）
- `README.md`（run要約）生成は任意

## Non-goals
- generate/qc/viz の本格実装（別タスク）
- 外部MLOps連携

## Acceptance Criteria (MUST)
- [ ] すべての Process が同じ方法で artifact を作れる（API統一）
- [ ] meta.json の必須フィールドが揃う（docs/04）
- [ ] `config_hash` が同一設定の2回実行で一致する（run_name/hydraに依存しない）
- [ ] 生成物が run dir 外へ出ない

## Verification (MUST)
以下は自動化（autodev/verifiers.py）で実行されますが、人手で確認する場合のコマンド例です。

1) doctor を2回実行
```bash
python -m synthlab.cli.main process=doctor seed=1
python -m synthlab.cli.main process=doctor seed=1
```

2) 最新の `runs/*/doctor/` の中に以下があること
- `config/resolved.yaml`
- `config/overrides.txt`
- `meta/meta.json`

3) `meta/meta.json` の `config_hash` が 2回で一致していること
- さらに `config/resolved.yaml` から canonical hash を計算した値と一致していること（docs/04の擬似コード）

## Implementation Notes
- **重要**: Hydra を使う場合でも、`.hydra/` のみに依存しないこと。
  - 契約は `config/resolved.yaml` と `config/overrides.txt` で固定する（docs/04）。
- `config_hash` は docs/04 の定義に従い、`hydra` と `run_name` を除外した canonical config から計算する。
  - run_name は `${now:...}` 等で変化しやすく、これを hash に含めると比較不能になるため。
- overrides.txt は取得できない環境がありうるため、P0では「空でも良いがファイルは必ず生成」で良い。
  - ただし将来、Hydraのoverride取得が可能なら埋める（TODO）

## DoD
- [ ] 最低1つのテスト（config_hashの安定性や必須ファイル存在）を追加（可能なら）
- [ ] docs/04 の契約に適合
