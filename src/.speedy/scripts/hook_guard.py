#!/usr/bin/env python3
"""
hook_guard.py — Opt-in Antigravity `PreToolUse` Lifecycle Hook cho Speedy DevKit (`runtime_enforced`).
Đọc JSON camelCase từ stdin theo đúng chuẩn Antigravity `hooks.json` và trả về quyết định trên stdout:
- `"deny"`: chặn cứng các lệnh xóa hủy diệt hệ thống hoặc thao tác đường dẫn trốn khỏi workspacePaths.
- `"force_ask"`: bắt buộc hỏi xác nhận người dùng đối với các thao tác Git/hệ thống không thể đảo ngược.
- `"allow"`: cho phép các thao tác đọc/sửa/chạy kiểm thử hợp lệ trong phạm vi workspace.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.dont_write_bytecode = True

_DENY_CMD_PATTERNS = (
    re.compile(r"(?:^|\s|;|&&|\|\|)rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:/(?:\s|;|$)|~(?:/|\s|;|$)|\$HOME\b)"),
    re.compile(r"(?:^|\s|;|&&|\|\|)rm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s+(?:/(?:\s|;|$)|~(?:/|\s|;|$)|\$HOME\b)"),
    re.compile(r"\bmkfs\b|\bdd\s+if="),
)

_FORCE_ASK_CMD_PATTERNS = (
    (re.compile(r"\bgit\s+push\b"), "Lệnh git push đẩy code lên remote cần người dùng xác nhận trực tiếp."),
    (re.compile(r"\bgit\s+tag\b"), "Tạo/xóa git tag phát hành cần người dùng xác nhận trực tiếp."),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard có nguy cơ xóa thay đổi chưa lưu."),
    (re.compile(r"\bgit\s+clean\b"), "git clean xóa file untracked trên đĩa."),
    (re.compile(r"\bgit\s+rebase\b"), "git rebase viết lại lịch sử commit."),
    (re.compile(r"(?:^|\s)sudo\s+"), "Lệnh nâng quyền sudo bắt buộc có sự đồng ý của người dùng."),
)


def _is_inside_any_workspace(target_path: str, workspace_paths: List[str], cwd: str) -> bool:
    roots = [Path(p).expanduser().resolve() for p in workspace_paths if p]
    if not roots and cwd:
        roots = [Path(cwd).expanduser().resolve()]
    if not roots:
        return True

    cand = Path(target_path).expanduser()
    base = Path(cwd).expanduser().resolve() if cwd else roots[0]
    resolved = (base / cand).resolve(strict=False) if not cand.is_absolute() else cand.resolve(strict=False)

    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def evaluate_pre_tool_use(payload: Dict[str, Any]) -> Dict[str, Any]:
    tool_call = payload.get("toolCall") or {}
    tool_name = str(tool_call.get("name") or "").lower()
    args = tool_call.get("args") or {}
    ws_paths = [str(p) for p in (payload.get("workspacePaths") or [])]
    cwd = str(payload.get("cwd") or (ws_paths[0] if ws_paths else ""))

    # 1. Kiểm tra đường dẫn file đối với các công cụ đọc/ghi/sửa file
    for path_key in ("Path", "AbsolutePath", "TargetFile", "file_path", "path"):
        if path_key in args and args[path_key]:
            target_str = str(args[path_key])
            if not _is_inside_any_workspace(target_str, ws_paths, cwd):
                return {
                    "decision": "deny",
                    "reason": f"Speedy Guard chặn truy cập đường dẫn nằm ngoài workspace: {target_str}",
                }

    # 2. Kiểm tra lệnh shell trong run_command
    if tool_name == "run_command":
        cmd_line = str(args.get("CommandLine") or args.get("command") or "")
        for deny_re in _DENY_CMD_PATTERNS:
            if deny_re.search(cmd_line):
                return {
                    "decision": "deny",
                    "reason": "Speedy Guard chặn cứng lệnh phá hủy hệ thống ngoài phạm vi an toàn.",
                }
        for ask_re, reason in _FORCE_ASK_CMD_PATTERNS:
            if ask_re.search(cmd_line):
                return {
                    "decision": "force_ask",
                    "reason": reason,
                }

    return {"decision": "allow"}


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"decision": "allow"}))
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))
        return 0

    result = evaluate_pre_tool_use(payload if isinstance(payload, dict) else {})
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
