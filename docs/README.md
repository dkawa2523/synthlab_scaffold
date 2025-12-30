# docs/README — 不変契約の読み方

この docs/ 配下は「開発中の不変契約」です。
以後、Codex/人間の実装・タスク・レビューは、必ずここを根拠にします。
**不変契約の変更は例外扱い**とし、必ず docs/00 の手順（blocked運用）に従って変更します。

## 読む順（推奨）
1. 00_INVARIANTS.md  
   - 最重要：再現性・比較可能性・skew禁止・Process/Artifactの定義
2. 01_ARCHITECTURE.md  
   - 依存方向・拡張方針・コード肥大化防止の構造
3. 03_CONFIG_CONVENTIONS.md  
   - Hydra（YAML）運用の規約：group/override/run dir/seed
4. 04_ARTIFACTS_AND_VERSIONING.md  
   - 出力契約：config/meta/metrics/plots/data 等
5. 10_PROCESS_CATALOG.md  
   - Process一覧と I/O（generate/qc/viz/export/train/eval…）
6. 11_PLUGIN_REGISTRY.md  
   - 追加・改良のための登録規約（pattern/size/メトリクス/可視化）
7. 09_EVALUATION_PROTOCOL.md  
   - 生成品質/QC/下流学習評価の比較ルール（seed/split/metrics）
8. 05_SECURITY_SECRETS.md  
   - 秘密情報・権限・ネットワーク・実測データ扱い
9. 12_INTEGRATIONS_READY.md  
   - 将来の MLOps 連携（今は入れないが見越す）
10. 20_EXAMPLES.md  
   - generate→qc→viz の最短手順と override 例

## この基盤が守ること（要約）
- Hydra config が真実：実行時に解決された config を artifact として保存する
- Process は「入力→出力」を固定し、横断的に比較可能にする
- plugin で拡張し、巨大な if/else を作らない
- artifact で結果を固定し、後から解析・可視化・学習に使える

## TODO（根拠が無いもの）
- ライセンス方針（MIT/Apache2/社内クローズ等）: TODO
- 実測データの取り込みI/O（社内ストレージ/権限）: TODO
