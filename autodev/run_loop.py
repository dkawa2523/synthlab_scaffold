\
#!/usr/bin/env python3
"""
autodev/run_loop.py (v2.2)

目的:
- work/queue.json と work/tasks/*.md と docs/ を読み、
  Codex CLI (codex exec) で "1タスクずつ" 実装→検証→進捗更新を自動化する。

今回の修正（T0003で詰まる問題への対策）:
- codex exec の read-only 既定を回避するため、--full-auto をデフォルトにする
- verification 失敗時、ログ/診断情報を次プロンプトに確実に注入する
- T0003 (artifact contract) は専用 verifier を実装（config_hash 安定性と必須ファイル検証）
- codex が質問して止まる場合、"自動回答" を次プロンプトに付与して前に進める

前提:
- 本ツールは repo ルートで実行すること
- docs/00_INVARIANTS.md を最上位契約として扱う
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # PyYAML

from verifiers import verify_task, VerificationResult


# ----------------------------
# IO helpers
# ----------------------------
def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_stamp() -> str:
    # マイクロ秒まで含めて衝突を避ける
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def read_text_safe(path: Path, limit: int = 200_000) -> str:
    try:
        s = path.read_text(encoding="utf-8", errors="replace")
        if len(s) > limit:
            return s[:limit] + "\n...[truncated]...\n"
        return s
    except FileNotFoundError:
        return ""


# ----------------------------
# Queue selection
# ----------------------------
def deps_satisfied(item: dict, done_ids: set) -> bool:
    deps = item.get("depends_on") or []
    return all(d in done_ids for d in deps)


def choose_next_task(queue: List[dict]) -> Optional[dict]:
    # doing があれば最優先
    doing = [q for q in queue if q.get("status") == "doing"]
    if doing:
        return doing[0]
    done = {q["id"] for q in queue if q.get("status") == "done"}
    # todo のうち depends_on を満たす最初のもの
    for q in queue:
        if q.get("status") != "todo":
            continue
        if deps_satisfied(q, done):
            return q
    return None


# ----------------------------
# Codex capability detection
# ----------------------------
@dataclasses.dataclass
class CodexCaps:
    has_full_auto: bool = True
    has_ask_for_approval: bool = True
    has_sandbox: bool = True
    has_yolo: bool = True
    has_output_last_message: bool = True


def detect_codex_caps(codex_exe: str) -> CodexCaps:
    """
    codex exec --help を見て対応フラグを判定する。
    環境差分（CLIバージョン差）で落ちないようにする。
    """
    try:
        p = subprocess.run(
            [codex_exe, "exec", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        txt = p.stdout or ""
    except FileNotFoundError:
        return CodexCaps(
            has_full_auto=False,
            has_ask_for_approval=False,
            has_sandbox=False,
            has_yolo=False,
            has_output_last_message=False,
        )

    def has(flag: str) -> bool:
        return flag in txt

    return CodexCaps(
        has_full_auto=has("--full-auto"),
        has_ask_for_approval=has("--ask-for-approval"),
        has_sandbox=has("--sandbox"),
        has_yolo=has("--yolo"),
        has_output_last_message=has("--output-last-message"),
    )


# ----------------------------
# Prompt building
# ----------------------------
QUESTION_PATTERNS = [
    r"\bplease confirm\b",
    r"\bshould i\b",
    r"\bcan you confirm\b",
    r"\bwhich (?:one|option)\b",
    r"\bdo you want me to\b",
    r"\bwould you like\b",
    r"\bどちら\b",
    r"\b確認\b",
]


def looks_like_question(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    # '? だけ' では誤検知しやすいので、フレーズ中心で検知
    return any(re.search(pat, t, re.IGNORECASE) for pat in QUESTION_PATTERNS)


def auto_answer_for(task_id: str, last_message: str) -> str:
    """
    Codexが質問して止まるのを避けるための自動回答。
    タスク固有で安全な既定回答を返す。
    """
    msg = (last_message or "").lower()
    if task_id == "T0003":
        # T0003で多い迷いどころ（config_hashの定義）
        return (
            "自動回答: config_hash は run_name や hydra など実行時に変化するキーを除外した "
            "『canonicalized resolved config』から計算してください。"
            "overrides.txt は取得できない場合は空で良いが、ファイルは必ず作成。"
            "質問せずにこの方針で実装を完了してください。"
        )
    # 一般既定
    return (
        "自動回答: 質問せずに、docs/00 と当該Taskの Scope/Contracts に最も整合する "
        "『最小実装で安全な既定』を選んで進めてください。"
    )


def build_prompt(
    repo_root: Path,
    task: dict,
    cfg: dict,
    attempt: int,
    failure_context: str,
    last_codex_message: str,
    escalated: bool,
) -> str:
    """
    Codex に渡すプロンプト本文を生成する。
    - docs の参照順
    - 該当 task md
    - skills のパス
    - 失敗ログ（verification/codex）
    """
    task_id = task["id"]
    title = task.get("title", "")
    contracts = task.get("contracts", [])
    skills = task.get("skills", [])

    # skills -> paths
    skill_registry_path = repo_root / "agentskills/skill_registry.json"
    skill_map = {}
    if skill_registry_path.exists():
        reg = load_json(skill_registry_path)
        for s in reg.get("skills", []):
            skill_map[s["id"]] = s["path"]
    skill_paths = [skill_map.get(s, "") for s in skills if skill_map.get(s)]

    task_md_path = Path(task.get("path", ""))
    if not task_md_path.is_absolute():
        task_md_path = repo_root / task_md_path

    lines: List[str] = []
    lines.append(f"# AUTODEV TASK RUN\n")
    lines.append(f"Target Task: {task_id} — {title}\n")

    lines.append("## Contracts (MUST READ)\n")
    for c in contracts:
        lines.append(f"- {c}")
    lines.append("")

    lines.append("## Skills to follow\n")
    for sp in skill_paths:
        lines.append(f"- {sp}")
    lines.append("")

    # strict anti-question instruction
    lines.append("## Hard rules (no stalls)\n")
    lines.append("- Do NOT ask the user questions. Make reasonable defaults and proceed.")
    lines.append("- If ambiguity exists, choose the option that preserves docs/00 invariants and is minimal.")
    lines.append("- Always keep changes small & reviewable; list files changed at the end.")
    lines.append("")

    if cfg.get("policy", {}).get("enforce_no_questions", True):
        lines.append("## AutoDev policy\n")
        lines.append("- If you ask questions/confirmation, the loop will treat it as failure and retry.")
        lines.append("")

    if looks_like_question(last_codex_message):
        lines.append("## AUTO-ANSWER (use this and proceed)\n")
        lines.append(auto_answer_for(task_id, last_codex_message))
        lines.append("")

    if failure_context.strip():
        lines.append("## Previous failure context (MUST FIX)\n")
        lines.append(failure_context.strip())
        lines.append("")

    if escalated:
        lines.append("## Escalation mode\n")
        lines.append("- You must open the failing logs mentioned above and fix the root cause.")
        lines.append("- Run the verification command locally (in this workspace) until it passes.")
        lines.append("- Do not change docs contracts unless absolutely necessary; if needed, implement TODO and proceed.")
        lines.append("")

    # include the task md itself (so codex doesn't need to open)
    if task_md_path.exists():
        lines.append("## Task file content\n")
        lines.append(f"(from {task_md_path.as_posix()})\n")
        lines.append("```md")
        lines.append(read_text_safe(task_md_path, limit=120_000))
        lines.append("```")
        lines.append("")
    else:
        lines.append("## Task file content\n")
        lines.append(f"ERROR: missing task file at {task_md_path.as_posix()}\n")

    # include key doc snippets (only docs/00 + task contracts)
    def add_doc(path_str: str):
        p = repo_root / path_str
        if p.exists():
            lines.append(f"## Contract: {path_str}\n```md\n{read_text_safe(p, limit=80_000)}\n```\n")
        else:
            lines.append(f"## Contract: {path_str}\nMISSING FILE: {path_str}\n")

    # Always include docs/00 first if present.
    add_doc("docs/00_INVARIANTS.md")
    for c in contracts:
        if c == "docs/00_INVARIANTS.md":
            continue
        add_doc(c)

    lines.append("## Deliverables\n")
    lines.append("- Implement changes to satisfy Acceptance Criteria and Verification.")
    lines.append("- Print a concise summary: files changed + how to run verification.")
    return "\n".join(lines)


# ----------------------------
# Codex execution
# ----------------------------
def run_codex_exec(
    repo_root: Path,
    cfg: dict,
    caps: CodexCaps,
    prompt_path: Path,
    out_log: Path,
    out_last_message: Path,
) -> Tuple[int, str]:
    """
    codex exec を非対話で実行し、stdout/stderr をログへ保存。
    最終メッセージも保存（対応フラグが無い場合はstdout末尾を採用）。
    """
    codex_exe = cfg["codex"]["executable"]
    cmd = [codex_exe, "exec"]

    # flags (only if supported)
    if cfg["codex"].get("full_auto", True) and caps.has_full_auto:
        cmd += ["--full-auto"]
    if cfg["codex"].get("use_yolo", False) and caps.has_yolo:
        cmd += ["--yolo"]
    if caps.has_ask_for_approval:
        cmd += ["--ask-for-approval", str(cfg["codex"].get("ask_for_approval", "never"))]
    if caps.has_sandbox:
        cmd += ["--sandbox", str(cfg["codex"].get("sandbox", "workspace-write"))]
    if caps.has_output_last_message:
        cmd += ["--output-last-message", str(out_last_message)]

    # prompt is read from stdin
    cmd += ["-"]  # read prompt from stdin

    prompt_text = prompt_path.read_text(encoding="utf-8")
    p = subprocess.run(
        cmd,
        input=prompt_text,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    out_log.write_text(p.stdout or "", encoding="utf-8")

    last_message = ""
    if out_last_message.exists():
        last_message = read_text_safe(out_last_message, limit=50_000)
    else:
        # fallback: take tail of stdout
        last_message = (p.stdout or "")[-50_000:]
        out_last_message.write_text(last_message, encoding="utf-8")
    return p.returncode, last_message


# ----------------------------
# Main loop
# ----------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="Run continuously until no runnable tasks.")
    ap.add_argument("--once", action="store_true", help="Run at most one task attempt.")
    args = ap.parse_args()

    repo_root = Path.cwd()
    cfg_path = repo_root / "autodev/config.yaml"
    if not cfg_path.exists():
        print("ERROR: autodev/config.yaml not found. Run from repo root.", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)

    logs_dir = repo_root / cfg["paths"]["logs_dir"]
    logs_dir.mkdir(parents=True, exist_ok=True)

    queue_path = repo_root / cfg["paths"]["queue_file"]
    if not queue_path.exists():
        print("ERROR: work/queue.json not found.", file=sys.stderr)
        return 2

    # codex capability detection
    caps = detect_codex_caps(cfg["codex"]["executable"])
    save_json(logs_dir / "preflight_codex_caps.json", dataclasses.asdict(caps))

    state_path = repo_root / cfg["paths"]["state_file"]
    state = load_json(state_path) if state_path.exists() else {}

    while True:
        queue = load_json(queue_path)
        task = choose_next_task(queue)
        if not task:
            print("No runnable tasks. Exiting.")
            return 0

        task_id = task["id"]
        # mark doing if todo
        for q in queue:
            if q["id"] == task_id and q.get("status") == "todo":
                q["status"] = "doing"
        save_json(queue_path, queue)

        max_attempts = int(cfg["loop"].get("max_attempts_per_task", 12))
        sleep_s = float(cfg["loop"].get("sleep_seconds_between_attempts", 0.0))
        escalate_after = int(cfg.get("policy", {}).get("escalate_after_attempts", 3))

        attempt = int(state.get("attempt", 0)) if state.get("task_id") == task_id else 0
        last_failure_context = state.get("last_failure_context", "") if state.get("task_id") == task_id else ""
        last_codex_message = state.get("last_codex_message", "") if state.get("task_id") == task_id else ""

        for i in range(attempt + 1, max_attempts + 1):
            stamp = now_stamp()
            prompt_path = logs_dir / f"{stamp}_{task_id}_a{i}_prompt.md"
            codex_log = logs_dir / f"{stamp}_{task_id}_a{i}_codex.log"
            last_msg_path = logs_dir / f"{stamp}_{task_id}_a{i}_codex_last_message.md"
            verify_log = logs_dir / f"{stamp}_{task_id}_a{i}_verification.log"

            escalated = i >= escalate_after

            prompt_text = build_prompt(
                repo_root=repo_root,
                task=task,
                cfg=cfg,
                attempt=i,
                failure_context=last_failure_context,
                last_codex_message=last_codex_message,
                escalated=escalated,
            )
            prompt_path.write_text(prompt_text, encoding="utf-8")

            print(f"\n=== [{task_id}] attempt {i} ===")
            print(f"Running codex exec... (prompt: {prompt_path})")

            rc, last_message = run_codex_exec(
                repo_root=repo_root,
                cfg=cfg,
                caps=caps,
                prompt_path=prompt_path,
                out_log=codex_log,
                out_last_message=last_msg_path,
            )

            # update state
            state = {
                "task_id": task_id,
                "attempt": i,
                "last_codex_message": last_message,
                "last_prompt": str(prompt_path),
                "last_codex_log": str(codex_log),
            }
            save_json(state_path, state)

            if rc != 0:
                failure = f"FAIL: codex exec returned non-zero ({rc}). See log: {codex_log}"
                print(failure)
                last_failure_context = f"{failure}\n\n--- codex log tail ---\n{read_text_safe(codex_log, limit=20_000)[-4000:]}"
                state["last_failure_context"] = last_failure_context
                save_json(state_path, state)
                time.sleep(sleep_s)
                continue

            if cfg.get("policy", {}).get("enforce_no_questions", True) and looks_like_question(last_message):
                failure = "FAIL: Codex asked for confirmation/questions; retrying same task with AUTO-ANSWER."
                print(failure)
                last_failure_context = (
                    f"{failure}\n\n--- last message ---\n{last_message}\n"
                )
                state["last_failure_context"] = last_failure_context
                save_json(state_path, state)
                time.sleep(sleep_s)
                continue

            print("Running verification...")
            vr: VerificationResult = verify_task(task_id=task_id, repo_root=repo_root, cfg=cfg, out_log=verify_log)

            if vr.ok:
                print(f"PASS: {task_id} verification passed.")
                # mark done
                queue = load_json(queue_path)
                for q in queue:
                    if q["id"] == task_id:
                        q["status"] = "done"
                        q["last_result"] = {"ok": True, "timestamp": stamp, "log": str(verify_log)}
                save_json(queue_path, queue)
                # clear state if next task
                state = {"task_id": None, "attempt": 0}
                save_json(state_path, state)
                break
            else:
                print(f"FAIL: {task_id} verification failed. Will retry same task.")
                failure_context = f"{vr.summary}\n\n--- verification log ---\n{read_text_safe(verify_log, limit=40_000)}"
                # persist
                state["last_failure_context"] = failure_context
                state["last_verification_log"] = str(verify_log)
                save_json(state_path, state)
                last_failure_context = failure_context
                last_codex_message = last_message
                time.sleep(sleep_s)
                continue
        else:
            # exceeded attempts
            print(f"BLOCKED: {task_id} exceeded max attempts ({max_attempts}).")
            queue = load_json(queue_path)
            for q in queue:
                if q["id"] == task_id:
                    q["status"] = "blocked"
                    q["blocked_reason"] = f"Exceeded max attempts ({max_attempts}). See autodev/state.json and logs."
            save_json(queue_path, queue)
            return 1

        if args.once:
            return 0

        if not args.loop:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
