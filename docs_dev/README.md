# Docs (読む順)

この `docs/` は **SynthLab Scaffold（wafer_particles）** の設計・運用・拡張を、レビュー/保守/追加開発しやすい形にまとめた開発者向けドキュメントです。

## 推奨の読む順

1. **index.md** – 何ができるか / どう使うか（Quickstart + 全体像）
2. **architecture.md** – レイヤ構造と依存方向、設計の狙い
3. **config_conventions.md** – Hydra設定の規約（YAMLが真実）
4. **process_catalog.md** – `process=` ごとのI/O、実行例
5. **patterns.md** – パターン一覧（C/K/O）とパラメータ設計
6. **size_models.md** – 粒径分布モデル（複数分布混在・per_sample含む）
7. **labeling.md** – ラベル階層（外部spec）と運用設計
8. **artifacts.md** – 出力物（runs/）の契約、バージョニング
9. **developer_guide.md** – 新規パターン/分布/Process追加の手順（チェックリスト）
10. **testing.md** – テストと品質ゲート（doctor/pytest/smoke）
11. **roadmap.md** – 今後の拡張計画と開発残件

> NOTE: 実装の詳細（正確なキー名/カラム名/出力パス）は、リポジトリ内の `schema` と `doctor` と `conf/` が真実です。
