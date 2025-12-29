# 12_INTEGRATIONS_READY — 「今は入れないが見越す」チェックリスト

この文書は、将来 ClearML/MLflow/W&B/DVC/HF Datasets 等を導入する際の
“後戻りしないための準備状況” を定義する。

## 1. 共通チェック
- [ ] run artifact に resolved config が保存される（docs/04）
- [ ] meta.json に seed/config_hash/git_sha がある
- [ ] metrics が機械可読（json/csv）である
- [ ] data が学習に適した形式（parquet推奨）である
- [ ] schema_version が明示されている

## 2. MLflow/Weights&Biases（例）
- [ ] run_id と紐付け可能な “experiment name” がある
- [ ] metrics を step/epoch 付きで拡張できる設計
- [ ] artifact のパス設計が固定（相対参照で再配置可能）

## 3. DVC/データレイク
- [ ] dataset_id（config hash）が確定し manifest に書かれる
- [ ] 生成物が巨大化しても分割/圧縮/更新単位が設計されている
- [ ] 実測データの取り扱いが docs/05 に沿う（権限/監査）

## 4. TODO
- 社内標準のMLOpsツールが決まったらチェック項目を具体化: TODO
