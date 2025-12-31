# autodev v2.2 patch

このzipは `autodev/` と一部 docs/work の修正パッチです（T0003詰まり対策）。

## 適用方法（既存リポジトリに上書き）
repo ルートで展開してください（同名ファイルは上書きされます）。

例:
```bash
unzip synthlab_autodev_patch_v2_2.zip -d /path/to/synthlab_scaffold
```

## 重要な変更点
- T0003 の verification を専用化（config_hash安定性 + 必須ファイル + canonical hash一致）
- config_hash の定義を docs/04 に明記（hydra/run_name除外）
- codex exec を --full-auto 既定に（read-only回避）

## blocked を解除して再実行する
```bash
python autodev/reset_task.py T0003 --to todo --clear-blocked-reason --clear-attempts --clear-last-failure
python autodev/run_loop.py --loop
```
