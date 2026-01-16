# Developer Guide（拡張開発ガイド）

このドキュメントは、開発者が **新しいパターン/粒径分布/Process** を追加する際の手順をチェックリスト化したものです。

---

## 1. 新しいPatternを追加する

### 1.1 追加するファイル
| 追加物 | 目的 | 例（パスは概念） |
|---|---|---|
| Pattern実装 | 生成ロジック | `src/.../wafer_particles/generators/patterns/<new>.py` |
| パターン設定YAML | Hydraから選べるように | `conf/wafer_particles/patterns/<new>.yaml` |
| Registry登録 | 自動認識 | `registry.py` のデコレータ or 登録リスト |
| テスト | 破綻検知 | `tests/test_patterns_smoke.py` 等 |
| docs更新 | レビュー性 | `docs/patterns.md` |

### 1.2 実装ルール（絶対）
| ルール | 理由 |
|---|---|
| wafer内制約を守る | 物理破綻防止 |
| RNGは引数から受け取る | 決定論の担保 |
| param_spaceで振れるようにする | 固定形状の過学習防止 |
| params_schemaを整備 | doctor / docs / UIのため |

### 1.3 チェックリスト（DoD）
- [ ] `doctor` が PASS
- [ ] `pytest` が PASS
- [ ] smoke config（小規模 generate）が PASS
- [ ] `patterns.md` に追記
- [ ] ベンチに入れるか判断し、必要なら `conf/benchmarks/` 更新

---

## 2. 新しいSizeModelを追加する

### 2.1 追加するファイル
| 追加物 | 目的 | 例 |
|---|---|---|
| SizeModel実装 | サンプリング関数 | `src/.../size_models/<new>.py` |
| size_models YAML | パラメータ指定 | `conf/wafer_particles/size_models/<new>.yaml` |
| doctor ルール | パラメータ検証 | `doctor` のチェック追加 |
| テスト | clamp/再現性/重尾 | `tests/test_size_models.py` |
| docs更新 | 利用者向け | `docs/size_models.md` |

### 2.2 実装ルール
| ルール | 理由 |
|---|---|
| `min_um/max_um` clamp を必ず通す | 物理/計測範囲の逸脱を防ぐ |
| per_sample のときパラメータを samples に保存 | 後から解析できないと詰む |
| selection（mix）に入れる場合、比率の正規化を明示 | データセット構成が追跡可能になる |

---

## 3. 新しいProcessを追加する

### 3.1 追加する場所
| 追加物 | 目的 |
|---|---|
| framework の dispatch | `process=<name>` を解決 |
| domain の実装 | 実処理（I/O） |
| conf の group | Hydraで選べるように |
| docs/process_catalog 更新 | I/O契約を明文化 |
| tests | 回帰防止 |

### 3.2 I/O契約のテンプレ
- 入力: `input_dir`（run） or config
- 出力: `runs/<timestamp>_<process>/...` に meta/data/reports/plots
- 失敗条件: doctor/QCで検出できるか

---

## 4. “パターン追加”を運用で破綻させないコツ

### 4.1 ラベル粒度を上げすぎない
- fineは増えてよいが、macroは抑える（10〜数十）
- 外部specの `similarity_groups` を用意して運用側で再編できるようにする

### 4.2 既存パターンと被る場合
- 被りを恐れて削るより、**「原因が違う」なら保持**する（K系の思想）
- ただしベンチでは macro に集約して扱えるようにする

### 4.3 比較可能性
- 破壊的変更は v2 config を切る
- dataset card に必ず構成を記録する

---

## 5. 開発支援（AutoDev/Codex）

AutoDev（`autodev/run_loop.py`）は、`work/tasks/` のタスク定義を読み、Codex CLI を使って実装→検証をループします。

- タスクは「実装単位」に分割し、Acceptance Criteria と Verification を必須にする
- 1タスクが未完のまま次に進まない（verifierが PASS するまで繰り返す）
- Codexが質問しそうな点は、タスク.mdに **決め打ち**の方針を明記する

