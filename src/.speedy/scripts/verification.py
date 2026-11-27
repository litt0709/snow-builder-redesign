"""
verification.py — Lập kế hoạch kiểm thử theo tác động (impact-based), thực thi runner an toàn,
tách bounded stdout summary khỏi file evidence đầy đủ đã làm sạch, và phát hiện Test Laundering.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from contracts import ErrorCode, SpeedyError, WorkspaceLayout, resolve_within_scope, validate_sid
from scan import scan_project
from storage import (
    atomic_write_text,
    compute_workspace_snapshot,
    load_session_state,
    mutate_session_state_cas,
    session_dir_for,
    utc_now_iso,
)

VERIFY_LAYERS = ("env_init", "lint_type", "unit_integration", "build", "e2e")

_SECRET_MASK_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|cookie|passwd|password|secret|token|pat|credential)(\s*[=:]\s*)([^\s,;\"']+)"
)

_SKIP_ADDED_PATTERNS = (
    re.compile(r"^\+.*@(?:unittest\.)?skip(?:If|Unless)?\b"),
    re.compile(r"^\+.*@pytest\.mark\.(?:skip|xfail)\b"),
    re.compile(r"^\+.*\b(?:it|describe|test)\.skip\s*\("),
    re.compile(r"^\+.*\bSkipTest\s*\("),
)

_ASSERT_LINE_RE = re.compile(
    r"\b(?:assert\b|self\.assert\w+|expect\s*\(|assertEquals|assertTrue|assertFalse)"
)

_TEST_DEF_DELETED_RE = re.compile(r"^-\s*(?:async\s+)?(?:def\s+test_\w+|it\s*\(|test\s*\()")
_THRESHOLD_LOWERED_RE = re.compile(
    r"^[-+].*(?:fail_under|coverageThreshold|min_coverage|threshold)\s*[=:]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def mask_sensitive_output(raw_text: str) -> str:
    return _SECRET_MASK_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", raw_text or "")


def bounded_output_preview(sanitized_text: str, max_bytes: int = 4096) -> Dict[str, Any]:
    encoded = sanitized_text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return {
            "preview": sanitized_text,
            "truncated": False,
            "total_bytes": len(encoded),
            "next_byte_offset": None,
        }
    clipped = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return {
        "preview": clipped,
        "truncated": True,
        "total_bytes": len(encoded),
        "next_byte_offset": len(clipped.encode("utf-8")),
    }


def detect_test_laundering(
    diff_text: str,
    *,
    approved_ac_change: bool = False,
) -> Dict[str, Any]:
    """
    Phát hiện nguy cơ gian lận kiểm thử (Test Laundering — mục 3.14 specs/design.md):
    - Thêm cờ skip/xfail vào test.
    - Xóa hàm test đã có.
    - Xóa câu lệnh assert mà không thêm assert tương đương (khi yêu cầu AC không đổi).
    """
    findings: List[Dict[str, str]] = []
    if not diff_text or not diff_text.strip():
        return {"suspicious": False, "findings": []}

    current_file = ""
    is_test_file = False
    removed_asserts = 0
    added_asserts = 0

    def _flush_file_asserts() -> None:
        nonlocal removed_asserts, added_asserts
        if is_test_file and removed_asserts > added_asserts and not approved_ac_change:
            findings.append(
                {
                    "type": "assertion_removed",
                    "file": current_file or "unknown_test_file",
                    "detail": f"Đã xóa {removed_asserts} assertion nhưng chỉ thêm {added_asserts} assertion mà không có thay đổi AC được duyệt.",
                }
            )
        removed_asserts = 0
        added_asserts = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            _flush_file_asserts()
            current_file = line[6:].strip()
            low = current_file.lower()
            is_test_file = (
                "test" in low or "spec" in low or low.startswith(("tests/", "test/"))
            )
            continue
        if line.startswith(("--- ", "@@ ")):
            continue

        if any(pat.search(line) for pat in _SKIP_ADDED_PATTERNS):
            findings.append(
                {
                    "type": "test_skipped",
                    "file": current_file or "unknown",
                    "detail": f"Phát hiện thêm cờ bỏ qua kiểm thử: {line.strip()[:140]}",
                }
            )

        if is_test_file and _TEST_DEF_DELETED_RE.search(line) and not approved_ac_change:
            findings.append(
                {
                    "type": "test_deleted",
                    "file": current_file or "unknown",
                    "detail": f"Phát hiện xóa test case hiện hữu: {line.strip()[:140]}",
                }
            )

        if is_test_file:
            if line.startswith("-") and not line.startswith("---") and _ASSERT_LINE_RE.search(line):
                removed_asserts += 1
            elif line.startswith("+") and not line.startswith("+++") and _ASSERT_LINE_RE.search(line):
                added_asserts += 1

        if line.startswith(("+", "-")) and _THRESHOLD_LOWERED_RE.search(line) and not approved_ac_change:
            if line.startswith("+"):
                findings.append(
                    {
                        "type": "threshold_modified",
                        "file": current_file or "config",
                        "detail": f"Phát hiện thay đổi ngưỡng coverage/threshold chưa được duyệt: {line.strip()[:140]}",
                    }
                )

    _flush_file_asserts()
    return {
        "suspicious": len(findings) > 0,
        "approved_ac_change": approved_ac_change,
        "findings": findings,
    }


def build_verify_plan(
    layout: WorkspaceLayout,
    *,
    sid: Optional[str] = None,
    changed_paths: Optional[Sequence[str]] = None,
    explicit_checks: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Lập kế hoạch kiểm tra 5 tầng dựa trên công cụ thực tế của dự án và phạm vi file thay đổi."""
    scan_info = scan_project(layout, ".", sid=sid, use_cache=True)
    detected = scan_info.get("detected_tooling", {})
    overrides = explicit_checks or {}

    shared_config_touched = any(
        Path(p).name in {"package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod"}
        or "schema" in p.lower()
        or "config" in p.lower()
        for p in (changed_paths or [])
    )

    layers: List[Dict[str, Any]] = []
    # 1. env_init
    env_cmd = shlex.split(overrides["env_init"]) if overrides.get("env_init") else [sys.executable, "--version"]
    layers.append({"layer": "env_init", "command": env_cmd, "required": True, "reason": "Xác nhận runtime hoạt động."})

    # 2. lint_type
    lint_cmd = (
        shlex.split(overrides["lint_type"])
        if overrides.get("lint_type")
        else (detected.get("lint") or detected.get("typecheck"))
    )
    layers.append(
        {
            "layer": "lint_type",
            "command": lint_cmd,
            "required": bool(lint_cmd),
            "reason": "Kiểm tra cú pháp/kiểu dữ liệu." if lint_cmd else "Dự án chưa cấu hình công cụ lint/typecheck.",
        }
    )

    # 3. unit_integration
    unit_cmd = shlex.split(overrides["unit_integration"]) if overrides.get("unit_integration") else detected.get("test")
    layers.append(
        {
            "layer": "unit_integration",
            "command": unit_cmd,
            "required": bool(unit_cmd),
            "reason": "Chạy bộ kiểm thử phủ kín hành vi thay đổi." if unit_cmd else "Chưa phát hiện test runner mặc định.",
        }
    )

    # 4. build
    build_cmd = shlex.split(overrides["build"]) if overrides.get("build") else detected.get("build")
    layers.append(
        {
            "layer": "build",
            "command": build_cmd,
            "required": bool(build_cmd),
            "reason": "Kiểm tra đóng gói/build." if build_cmd else "Không có bước biên dịch riêng.",
        }
    )

    # 5. e2e
    e2e_cmd = shlex.split(overrides["e2e"]) if overrides.get("e2e") else None
    layers.append(
        {
            "layer": "e2e",
            "command": e2e_cmd,
            "required": bool(e2e_cmd),
            "reason": "Kiểm thử tích hợp đầu-cuối." if e2e_cmd else "Chỉ chạy khi có kịch bản E2E được cấu hình.",
        }
    )

    return {
        "sid": sid,
        "lang": scan_info.get("lang"),
        "changed_inputs": list(changed_paths or []),
        "escalate_full_suite": shared_config_touched or not changed_paths,
        "layers": layers,
    }


def run_verification(
    layout: WorkspaceLayout,
    *,
    sid: Optional[str] = None,
    explicit_checks: Optional[Dict[str, str]] = None,
    diff_file: Optional[str] = None,
    approved_ac_change: bool = False,
    timeout_seconds: int = 120,
    max_output_bytes: int = 4096,
) -> Dict[str, Any]:
    """
    Thực thi từng tầng kiểm tra bằng danh sách đối số (`shell=False`), không coi tầng chưa chạy là PASS,
    lưu toàn bộ bằng chứng đã làm sạch ra đĩa và cập nhật canonical `state.json` nếu có `sid`.
    """
    plan = build_verify_plan(layout, sid=sid, explicit_checks=explicit_checks)
    focus_paths: Optional[Sequence[str]] = None
    if sid:
        try:
            st = load_session_state(layout, sid)
            focus_paths = st.get("scope", {}).get("allowed_paths") or None
        except SpeedyError:
            focus_paths = None
    snapshot = compute_workspace_snapshot(layout.root, focus_paths=focus_paths)

    evidence_dir = (
        (session_dir_for(layout, sid) / "evidence")
        if sid
        else (layout.tmp_dir / "verify_evidence")
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    layer_results: List[Dict[str, Any]] = []
    any_failed = False
    ran_real_check = False

    for item in plan["layers"]:
        layer_name = item["layer"]
        cmd = item["command"]
        if not cmd:
            layer_results.append(
                {
                    "layer": layer_name,
                    "status": "NOT_APPLICABLE",
                    "command": None,
                    "exit_code": None,
                    "duration_ms": 0,
                    "reason": item["reason"],
                    "evidence_path": None,
                }
            )
            continue

        start_t = time.monotonic()
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(layout.root),
                capture_output=True,
                text=True,
                timeout=max(5, int(timeout_seconds)),
                env=env,
            )
            dur_ms = int((time.monotonic() - start_t) * 1000)
            combined_out = mask_sensitive_output((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
            ev_file = evidence_dir / f"{layer_name}.log"
            atomic_write_text(ev_file, combined_out + "\n")
            preview = bounded_output_preview(combined_out, max_bytes=max_output_bytes)

            status = "PASS" if proc.returncode == 0 else "FAIL"
            if layer_name != "env_init":
                ran_real_check = True
            if status == "FAIL":
                any_failed = True

            layer_results.append(
                {
                    "layer": layer_name,
                    "status": status,
                    "command": cmd,
                    "exit_code": proc.returncode,
                    "duration_ms": dur_ms,
                    "evidence_path": ev_file.relative_to(layout.root).as_posix(),
                    "output_preview": preview["preview"],
                    "truncated": preview["truncated"],
                    "total_output_bytes": preview["total_bytes"],
                    "next_byte_offset": preview["next_byte_offset"],
                }
            )
            # Fail-fast khi một tầng bắt buộc thất bại
            if status == "FAIL":
                break
        except subprocess.TimeoutExpired:
            any_failed = True
            layer_results.append(
                {
                    "layer": layer_name,
                    "status": "FAIL",
                    "command": cmd,
                    "exit_code": -1,
                    "duration_ms": int(timeout_seconds * 1000),
                    "reason": f"Quá thời gian chờ ({timeout_seconds}s).",
                    "evidence_path": None,
                }
            )
            break
        except FileNotFoundError as exc:
            any_failed = True
            layer_results.append(
                {
                    "layer": layer_name,
                    "status": "FAIL",
                    "command": cmd,
                    "exit_code": 127,
                    "duration_ms": 0,
                    "reason": f"Không tìm thấy công cụ thực thi: {exc}",
                    "evidence_path": None,
                }
            )
            break

    # Kiểm tra Test Laundering nếu có truyền diff_file hoặc phát hiện được git diff
    diff_content = ""
    if diff_file:
        dpath = resolve_within_scope(layout.root, diff_file)
        if dpath.is_file():
            diff_content = dpath.read_text(encoding="utf-8", errors="replace")
    else:
        try:
            git_proc = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(layout.root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if git_proc.returncode == 0:
                diff_content = git_proc.stdout
        except Exception:
            diff_content = ""

    laundering_report = detect_test_laundering(diff_content, approved_ac_change=approved_ac_change)
    if laundering_report["suspicious"]:
        any_failed = True

    overall = "FAIL" if any_failed else ("PASS" if ran_real_check else "PARTIAL_ENV_ONLY")
    summary = {
        "sid": sid,
        "overall_status": overall,
        "snapshot": snapshot,
        "layers": layer_results,
        "test_laundering": laundering_report,
        "verified_at": utc_now_iso(),
    }

    if sid:
        def _record(state: Dict[str, Any]) -> None:
            state.setdefault("verification", []).append(summary)
            state["code_snapshot"] = snapshot

        mutate_session_state_cas(layout, sid, _record, owner="verify_runner")

    if any_failed:
        raise SpeedyError(
            ErrorCode.VERIFICATION_FAILED,
            "Kiểm chứng thất bại hoặc phát hiện nghi vấn Test Laundering.",
            details=summary,
            remediation="Xem file evidence chi tiết để sửa nguyên nhân gốc trước khi chạy lại verify.",
        )

    return summary
