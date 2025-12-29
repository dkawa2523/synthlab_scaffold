# S70 — Visualization & DS Workflow (Data Scientist)

## 目的
- 生成した擬似データの中身を把握しやすくする（レビュー/説明/分析）
- 将来ドメインでも使える “可視化の骨格” を作る

## 参照（MUST）
- docs/04_ARTIFACTS_AND_VERSIONING.md
- docs/09_EVALUATION_PROTOCOL.md

## 手順
1) 最低限の可視化を揃える
   - wafer散布図（r/theta→x/y）
   - 半径ヒスト、角度ヒスト、粒径ヒスト
2) ラベル別の代表サンプルを保存
3) 図は plots/ に保存し、再実行で更新は新runへ（不変契約）
4) 解析導線（どの図を見るべきか）を README で補助

## 事故りやすい点
- 図だけ作って “粒子データとして壊れている” のに気づかない
- 可視化コードが 1ファイル巨大化

## DoD
- [ ] plots/ が artifact に残る
- [ ] ラベル別に最小限の図が揃う
- [ ] 図の解釈が docs/09 の指標と対応している
