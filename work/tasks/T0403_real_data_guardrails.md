# TASK: T0403 実測データ取扱いガードレール（誤コミット防止/パス規約/ログ最小化）(P0)

## Contracts (MUST READ)
- docs/05_SECURITY_SECRETS.md
- docs/00_INVARIANTS.md
- docs/03_CONFIG_CONVENTIONS.md
- docs/04_ARTIFACTS_AND_VERSIONING.md

## Summary
実測（機密）データの利用を見据え、**誤コミット・誤ログ・誤保存**を防ぐガードレールを導入する。

## Scope
- `.gitignore` に実測データ向けディレクトリ（例: `data_real/`, `real_data/`, `inputs/real/`）を追加
- Hydra config 規約:
  - 実測データのルートは `DATA_ROOT` など env 経由にする例を docs/05 に追記（TODOでも可）
- 可能なら `process=import_real` / `process=compare` 等で以下を実装
  - 入力ファイルの絶対パス/機密パスをログに出さない（最小化）
  - リポジトリ配下（cwd以下）からの実測ファイル読み込みを禁止/警告（誤コミット防止）
- docs/05 を更新し、運用の注意事項（やってはいけないこと）を明文化

## Non-goals
- 社内IAM/権限設計（別途）
- 暗号化ストレージ連携（別途）

## Acceptance Criteria
- [ ] 実測データが誤ってリポジトリに入る経路を塞ぐ（gitignore + 追加チェック）
- [ ] 実測ファイルパスをログに露出しない方針がコード/ドキュメントに反映されている
- [ ] `pytest` でガードレール（例: repo配下パス拒否）が検証できる

## Verification
- `pytest -q -k T0403`

## Implementation Notes
- “禁止/警告” の挙動は `policy.real_data.allow_repo_paths=false` のように config 化しても良い
