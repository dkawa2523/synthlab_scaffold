# 05_SECURITY_SECRETS — セキュリティ/秘密情報/権限

## 1. 秘密情報の原則（MUST）
- リポジトリに秘密情報をコミットしない
  - APIキー、トークン、社内URL、認証情報、個人情報
- 設定は Hydra YAML だが、秘密は env 経由にする（例：`DATA_ROOT=${oc.env:DATA_ROOT}`）
- `.env` はローカル利用のみ（gitignore）

## 2. 実測データ（もし扱う場合）
- 実測データは原則リポジトリ外（社内規定ストレージ）
- 実測データのルートは env 経由で指定する（例: `DATA_ROOT`, `REAL_PARTICLES_PATH`）
  - Hydra 例: `particles_path: ${oc.env:DATA_ROOT}/wafer/particles.parquet`
- repo 配下の実測入力はデフォルトで拒否（`policy.real_data.allow_repo_paths=false`）
  - テスト等で必要な場合のみ `true` を明示し、運用では戻す
- 実測データを repo 内の `data_real/` `real_data/` `inputs/real/` に置かない（gitignore でも持ち込まない）
- 実測入力のパスはログ/metrics に絶対パスを残さず、最小限の情報にする
- artifact に含める場合は匿名化・最小化・アクセス制御を TODO
- 実測データのスキーマ/取り扱い規程は会社ポリシーに依存（TODO）

## 3. ネットワーク/外部連携
- P0では外部ネットワーク連携は前提にしない
- 将来導入する場合は docs/12 のチェックリストを満たしてから

## 4. 権限と監査（TODO）
- CI/CD、クラウド、MLOpsツール導入時の権限設計: TODO
