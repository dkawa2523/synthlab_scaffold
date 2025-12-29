# 00_INVARIANTS — 不変条件（契約）

## 0. この文書の位置づけ
この文書は「以後すべての実装/タスク/レビューが従う不変契約」です。
例外は **blocked運用**でのみ許可します。

---

## 1. 用語
- **Domain**: データ型のまとまり（例：wafer_particles、画像、時系列）
- **Process**: 実行単位（generate/qc/viz/train/eval/export/doctor…）
- **Artifact**: Processの出力（runディレクトリ）。再現・比較の最小単位
- **Plugin**: 拡張点（pattern/size_model/metric/viz/process など）
- **Resolved Config**: Hydra で解決済みの設定（YAML）。真実の情報

---

## 2. 不変条件（MUST）
### 2.1 設定が真実（Config is the Source of Truth）
- すべての実行は Hydra 設定（YAML）で宣言される
- Artifact には必ず以下を保存する
  - 解決済み config（resolved.yaml）
  - override（overrides.txt）
  - seed
  - 実行環境メタ（OS/Python/依存）

### 2.2 再現性（Determinism）
- 乱数は **単一の seed** と **明示的な RNG 注入**で制御する
- グローバル乱数（np.random.* の暗黙利用、random モジュール直叩き）は禁止
- 同じ resolved config + seed から、同一データ・同一統計が再現できること

### 2.3 Processの純度（Process Purity）
- Process は「入力Artifact/入力ファイル → 出力Artifact」を明確にする
- Process は run ディレクトリ外に副作用を書かない（例外：明示された cache/ がある場合のみ）
- Process は構成上、他の Process の内部実装に依存しない（I/O契約に依存）

### 2.4 Artifactは追記・改変しない（Immutability）
- 生成済み artifact は原則「write-once」
- 再生成/改良は新しい run として出力する（比較可能性のため）
- 例外的な上書きは blocked運用でのみ許可

### 2.5 比較可能性（Comparability）
- 比較は「同一評価プロトコル（docs/09）」「同一スキーマ」「同一seed方針」でのみ行う
- 生成器の変更で評価が変わる場合、必ず差分を meta に残す（git sha / config hash）

### 2.6 Skew禁止（Train/Inference / Generate/Analyze のズレ禁止）
- 同じ artifact を入力にする解析/QC/viz は同じスキーマ・同じ前処理を用いる
- “見た目だけ合う” 生成（vizで見えるが粒子データとしては壊れている等）を禁止
- 変換（r,theta→x,y 等）は単一実装に統一し、複数実装の分岐を禁止

### 2.7 拡張はPluginで行う（No Big if/else）
- パターン追加、サイズモデル追加、評価指標追加、可視化追加は Plugin Registry を通す
- 巨大な条件分岐で増殖させない（コード肥大化・レビュー困難を防ぐ）

### 2.8 観測可能性（Observability）
- すべての run は metrics と plots を持つ（最低限）
- ログ（console.log相当）を run に残す（クラッシュ時に再現可能にする）

---

## 3. Blocked運用（不変契約の変更手順）
不変契約に抵触する変更が必要になった場合:

1) まず **blocked** の解除タスクを作る（work/tasks に追加）
   - 解除タスクは `unblocks: [対象タスクID]` を持つ  
2) docs の更新（どの不変条件がなぜ変わるか、影響範囲、移行手順）
3) 互換性/移行計画（artifact/schema/version の扱い）
4) Verification を通してから実装再開

---

## 4. TODO（根拠が無い点）
- 生成データを社内レイクに登録する正式手順（権限/監査）: TODO
- 実測データの匿名化・取り扱い規定（会社ポリシー依存）: TODO
