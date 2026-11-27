#!/usr/bin/env python3
"""
speedy_cli.py — Unified Deterministic CLI Harness cho Speedy DevKit & SNOW Builder (Antigravity IDE).
Zero-dependency (Python 3.11+ stdlib).

Quy ước giao tiếp:
- Kết quả thành công: JSON chuẩn duy nhất trên stdout, exit code = 0.
- Lỗi: JSON diagnostic có cấu trúc trên stderr, exit code != 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.dont_write_bytecode = True

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from adapters import get_antigravity_capabilities  # noqa: E402
from audit import finalize_audit, record_audit_event, start_audit  # noqa: E402
from audit_viewer import render_audit_dashboard  # noqa: E402
from benchmark import compare_paired_runs, evaluate_context_and_routing_suite  # noqa: E402
from catalog import build_catalog  # noqa: E402
from cleanup import run_cleanup  # noqa: E402
from context import (  # noqa: E402
    check_docs_freshness,
    compact_session_checkpoint,
    prepare_context_packet,
    promote_lesson_to_project,
    propose_lesson,
    query_cross_repo_registry,
    register_cross_repo_topic,
    stamp_source_ref_line,
)
from contracts import ErrorCode, SpeedyError, resolve_layout, resolve_within_scope  # noqa: E402
from docs_viewer import render_docs_site  # noqa: E402
from handoff import validate_handoff  # noqa: E402
from installer_core import rollback_from_backup, update_from_source  # noqa: E402
from lifecycle import (  # noqa: E402
    complete_stage,
    complete_worker_uow,
    create_session,
    list_sessions,
    record_gate_decision,
    register_worker_uow,
    resolve_target_sid,
    resume_session,
    transition_stage,
)
from policy import classify_intent, select_gemini_model  # noqa: E402
from repomap import build_repomap, query_repomap  # noqa: E402
from scaffold import scaffold_handoff  # noqa: E402
from scan import scan_project  # noqa: E402
from storage import load_session_state  # noqa: E402
from verification import build_verify_plan, run_verification  # noqa: E402


def _emit_ok(payload: Dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _emit_err(err: SpeedyError) -> int:
    print(json.dumps(err.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
    return err.exit_code


def _handle_session(layout, args: argparse.Namespace) -> int:
    action = args.session_action
    if action == "new":
        res = create_session(
            layout,
            slug=args.slug,
            goal=args.goal or args.slug,
            mode=args.mode,
            policy_profile=args.policy,
            execution_mode=args.execution_mode,
            allowed_paths=args.allow_path,
            forbidden_paths=args.forbid_path,
            command_ref=args.command_ref,
        )
        if not args.no_audit:
            aud = start_audit(
                layout,
                sid=res["sid"],
                slug=args.slug,
                goal=args.goal or args.slug,
                mode=res["mode"],
                policy=res["policy"],
                command_ref=args.command_ref,
                budget=res["budget"],
            )
            res["audit"] = aud
        return _emit_ok(res)

    if action == "list":
        sessions = list_sessions(layout)
        return _emit_ok({"count": len(sessions), "sessions": sessions})

    if action == "get":
        sid = resolve_target_sid(layout, args.sid, for_mutation=False)
        return _emit_ok(load_session_state(layout, sid))

    if action == "resume":
        return _emit_ok(resume_session(layout, args.sid))

    raise SpeedyError(ErrorCode.INVALID_INPUT, "Subcommand của session phải là: new | list | get | resume.")


def _handle_intent(layout, args: argparse.Namespace) -> int:
    del layout
    text = " ".join(args.text)
    return _emit_ok(classify_intent(text, target_paths=args.paths))


def _handle_model(layout, args: argparse.Namespace) -> int:
    del layout
    return _emit_ok(
        select_gemini_model(
            args.role,
            high_risk=args.high_risk,
            complex_architecture=args.complex,
            repeated_failure=args.repeated_failure,
        )
    )


def _handle_scan(layout, args: argparse.Namespace) -> int:
    return _emit_ok(scan_project(layout, args.path, sid=args.sid, use_cache=not args.no_cache))


def _handle_repomap(layout, args: argparse.Namespace) -> int:
    action = args.repomap_action
    if action == "query" or getattr(args, "query_text", None):
        kw = " ".join(args.keyword) if getattr(args, "keyword", None) else args.query_text
        return _emit_ok(query_repomap(layout, kw, root_dir=args.root, limit=args.limit, out_path=args.out))
    return _emit_ok(build_repomap(layout, root_dir=args.root, out_path=args.out, use_cache=not args.no_cache))


def _handle_catalog(layout, args: argparse.Namespace) -> int:
    return _emit_ok(build_catalog(layout, use_cache=not args.no_cache))


def _handle_capabilities(layout, args: argparse.Namespace) -> int:
    del args
    return _emit_ok(get_antigravity_capabilities(layout))


def _handle_scaffold(layout, args: argparse.Namespace) -> int:
    return _emit_ok(
        scaffold_handoff(
            layout,
            args.sid,
            args.stage,
            slug=args.slug or "task",
            overwrite=args.overwrite,
        )
    )


def _handle_handoff(layout, args: argparse.Namespace) -> int:
    if args.handoff_action != "validate":
        raise SpeedyError(ErrorCode.INVALID_INPUT, "Dùng: speedy_cli.py handoff validate --sid <SID> --stage <STAGE>")
    scope_allowed = None
    scope_forbidden = None
    try:
        st = load_session_state(layout, args.sid)
        scope_allowed = st.get("scope", {}).get("allowed_paths") or None
        scope_forbidden = st.get("scope", {}).get("forbidden_paths") or None
    except SpeedyError:
        pass
    res = validate_handoff(
        layout,
        args.sid,
        args.stage,
        allowed_paths=scope_allowed,
        forbidden_paths=scope_forbidden,
    )
    if not res["valid"]:
        raise SpeedyError(
            ErrorCode.CONTRACT_VIOLATION,
            f"Handoff chưa hợp lệ cho stage '{res['stage']}'.",
            stage=res["stage"],
            path=res["file_path"],
            details=res,
            exit_code=1,
        )
    return _emit_ok(res)


def _handle_state(layout, args: argparse.Namespace) -> int:
    if args.state_action == "get":
        sid = resolve_target_sid(layout, args.sid, for_mutation=False)
        return _emit_ok(load_session_state(layout, sid))
    if args.state_action == "transition":
        return _emit_ok(
            transition_stage(
                layout,
                sid=args.sid,
                stage=args.stage,
                target_status=args.status,
                expected_revision=args.expected_revision,
                failure_reason=args.reason,
                failure_command=args.command_name,
                has_new_hypothesis=args.new_hypothesis,
            )
        )
    if args.state_action == "uow":
        if args.uow_status in {"completed", "failed"}:
            return _emit_ok(
                complete_worker_uow(
                    layout,
                    sid=args.sid,
                    uow_id=args.uow_id,
                    status=args.uow_status,
                )
            )
        if not args.stage or not args.objective:
            raise SpeedyError(
                ErrorCode.INVALID_INPUT,
                "Đăng ký UoW mới bắt buộc truyền '--stage' và '--objective'.",
            )
        return _emit_ok(
            register_worker_uow(
                layout,
                sid=args.sid,
                uow_id=args.uow_id,
                stage=args.stage,
                objective=args.objective,
                write_paths=args.write_path or [],
            )
        )
    if args.state_action == "complete":
        return _emit_ok(complete_stage(layout, sid=args.sid, stage=args.stage))
    raise SpeedyError(ErrorCode.INVALID_INPUT, "Subcommand của state phải là: get | transition | complete | uow.")


def _handle_gate(layout, args: argparse.Namespace) -> int:
    return _emit_ok(
        record_gate_decision(
            layout,
            sid=args.sid,
            stage=args.stage,
            decision=args.gate_action,
            actor=args.actor,
            interaction_ref=args.interaction_ref,
            feedback=args.feedback,
            return_to_stage=getattr(args, "return_to", None),
        )
    )


def _handle_context(layout, args: argparse.Namespace) -> int:
    if args.context_action == "prepare":
        return _emit_ok(prepare_context_packet(layout, sid=args.sid, stage=args.stage, query=args.query))
    if args.context_action == "compact":
        return _emit_ok(compact_session_checkpoint(layout, sid=args.sid))
    raise SpeedyError(ErrorCode.INVALID_INPUT, "Subcommand của context phải là: prepare | compact.")


def _handle_knowledge(layout, args: argparse.Namespace) -> int:
    action = args.knowledge_action
    if action == "check-freshness":
        return _emit_ok(check_docs_freshness(layout))
    if action == "stamp-ref":
        return _emit_ok({"source_ref_line": stamp_source_ref_line(layout, args.source)})
    if action == "cross-repo":
        return _emit_ok(query_cross_repo_registry(layout, " ".join(args.query)))
    if action == "register-cross-repo":
        return _emit_ok(
            register_cross_repo_topic(
                layout,
                repo_id=args.repo_id,
                description=args.description or "",
                topic_id=args.topic_id,
                keywords=args.keyword or [],
                topic_rel_path=args.path,
                aliases=args.alias,
                local_path=args.local_path,
            )
        )
    if action == "propose-lesson":
        return _emit_ok(
            propose_lesson(
                layout,
                sid=args.sid,
                title=args.title,
                lesson=args.lesson,
                evidence_ref=args.evidence_ref,
            )
        )
    if action == "promote-lesson":
        return _emit_ok(
            promote_lesson_to_project(
                layout,
                sid=args.sid,
                lesson_id=args.lesson_id,
                actor=args.actor,
                interaction_ref=args.interaction_ref,
            )
        )
    raise SpeedyError(
        ErrorCode.INVALID_INPUT,
        "Subcommand của knowledge phải là: check-freshness | stamp-ref | cross-repo | register-cross-repo | propose-lesson | promote-lesson.",
    )


def _parse_kv_checks(pairs: list[str] | None) -> Dict[str, str]:
    checks: Dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise SpeedyError(
                ErrorCode.INVALID_INPUT,
                f"Tham số --check không hợp lệ ('{item}'); cần dạng '<layer>=<command>'.",
            )
        k, v = item.split("=", 1)
        checks[k.strip()] = v.strip()
    return checks


def _handle_verify(layout, args: argparse.Namespace) -> int:
    checks = _parse_kv_checks(getattr(args, "check", None))
    if args.verify_action == "plan":
        return _emit_ok(
            build_verify_plan(
                layout,
                sid=args.sid,
                changed_paths=args.changed_path,
                explicit_checks=checks,
            )
        )
    return _emit_ok(
        run_verification(
            layout,
            sid=args.sid,
            explicit_checks=checks,
            diff_file=args.diff_file,
            approved_ac_change=args.approved_ac_change,
            timeout_seconds=args.timeout,
        )
    )


def _handle_audit(layout, args: argparse.Namespace) -> int:
    action = args.audit_action
    if action == "start":
        return _emit_ok(
            start_audit(
                layout,
                sid=args.sid,
                slug=args.slug or "task",
                goal=args.goal or args.slug or "task",
                mode=args.mode,
                policy=args.policy,
                command_ref=args.command_ref,
                prompt_ref=args.prompt_ref,
            )
        )
    if action == "event":
        return _emit_ok(
            record_audit_event(
                layout,
                audit_dir=args.audit_dir,
                agent=args.agent,
                category=args.category,
                model=args.model,
                summary=args.summary,
                human_wait_ms=args.human_wait_ms,
                model_time_ms=args.model_time_ms,
                tool_time_ms=args.tool_time_ms,
            )
        )
    if action == "finalize":
        measured = None
        if args.usage_json:
            try:
                measured = json.loads(args.usage_json)
            except json.JSONDecodeError as exc:
                raise SpeedyError(ErrorCode.INVALID_INPUT, f"--usage-json không phải JSON hợp lệ: {exc}") from exc
        return _emit_ok(
            finalize_audit(
                layout,
                audit_dir=args.audit_dir,
                outcome=args.outcome,
                completion_level=args.completion_level,
                ac_passed=args.ac_passed,
                ac_total=args.ac_total,
                build_status=args.build_status,
                files_changed=args.files_changed,
                measured_usage=measured,
                usage_source=args.usage_source,
            )
        )
    raise SpeedyError(ErrorCode.INVALID_INPUT, "Subcommand của audit phải là: start | event | finalize.")


def _handle_docs_view(layout, args: argparse.Namespace) -> int:
    res = render_docs_site(
        layout,
        docs_dir=args.docs_dir,
        output_path=args.output,
        open_browser=args.open,
    )
    return _emit_ok(
        {
            "status": res.status,
            "path": str(res.path),
            "relative_path": res.path.relative_to(layout.root).as_posix(),
            "uri": res.path.as_uri(),
            "files_rendered": res.files_rendered,
        }
    )


def _handle_audit_view(layout, args: argparse.Namespace) -> int:
    res = render_audit_dashboard(
        layout,
        month=args.month,
        audit_dir=args.audit_dir,
        output_path=args.output,
        open_browser=args.open,
    )
    return _emit_ok(
        {
            "status": res.status,
            "path": str(res.path),
            "relative_path": res.path.relative_to(layout.root).as_posix(),
            "uri": res.path.as_uri(),
            "month": res.month,
            "tasks": res.tasks,
            "status_reason": res.status_reason,
            "message": res.message,
        }
    )


def _handle_cleanup(layout, args: argparse.Namespace) -> int:
    return _emit_ok(
        run_cleanup(
            layout,
            older_than_days=args.older_than,
            include_plans=args.include_plans,
            include_logs=args.include_logs,
            include_reports=args.include_reports,
            include_audit=args.include_audit,
            apply=args.apply,
        )
    )


def _handle_benchmark(layout, args: argparse.Namespace) -> int:
    from storage import read_json_safe

    if args.benchmark_action == "suite":
        tasks_data = read_json_safe(resolve_within_scope(layout.root, args.tasks_file))
        return _emit_ok(evaluate_context_and_routing_suite(layout, tasks_data.get("tasks", [])))
    if args.benchmark_action == "compare":
        base_data = read_json_safe(resolve_within_scope(layout.root, args.baseline))
        cand_data = read_json_safe(resolve_within_scope(layout.root, args.candidate))
        return _emit_ok(compare_paired_runs(base_data.get("trials", []), cand_data.get("trials", [])))
    raise SpeedyError(ErrorCode.INVALID_INPUT, "Subcommand của benchmark phải là: suite | compare.")


def _handle_update(layout, args: argparse.Namespace) -> int:
    if args.rollback:
        bdir = resolve_within_scope(layout.root, args.rollback)
        return _emit_ok(rollback_from_backup(bdir, layout.root))
    return _emit_ok(
        update_from_source(
            layout.root,
            source=args.source,
            ref=args.ref,
            dry_run=not args.apply,
            force_overwrite_conflicts=args.force_overwrite,
            allow_with_conflicts_skipped=args.skip_conflicts,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speedy_cli",
        description="Speedy DevKit v2.0 — Deterministic CLI Harness cho Antigravity IDE",
    )
    parser.add_argument("--workspace", "--base", dest="workspace", default=".", help="Thư mục gốc workspace (mặc định: .)")
    parser.add_argument("--layout", choices=["auto", "product", "builder"], default="auto", help="Kiểu layout workspace")
    sub = parser.add_subparsers(dest="command")

    # 1. session
    p_sess = sub.add_parser("session", help="Khởi tạo, liệt kê, đọc và resume session")
    sess_sub = p_sess.add_subparsers(dest="session_action")

    s_new = sess_sub.add_parser("new", help="Tạo session mới")
    s_new.add_argument("--slug", required=True, help="Slug ngắn mô tả task")
    s_new.add_argument("--goal", help="Mục tiêu đầy đủ của task")
    s_new.add_argument("--mode", choices=["setup", "feature", "fix", "simple", "verify"])
    s_new.add_argument("--policy", choices=["strict", "balanced"], default=None)
    s_new.add_argument("--execution-mode", choices=["antigravity_subagent", "sequential_roles"], default="antigravity_subagent")
    s_new.add_argument("--allow-path", action="append", help="Đường dẫn nằm trong scope (lặp lại được)")
    s_new.add_argument("--forbid-path", action="append", help="Đường dẫn cấm chạm vào (lặp lại được)")
    s_new.add_argument("--command-ref", help="Lệnh/skill khởi phát")
    s_new.add_argument("--no-audit", action="store_true", help="Không tự tạo thư mục audit lúc khởi tạo")

    sess_sub.add_parser("list", help="Liệt kê các session")
    s_get = sess_sub.add_parser("get", help="Đọc canonical state của session")
    s_get.add_argument("--sid", help="Session ID")
    s_res = sess_sub.add_parser("resume", help="Kiểm tra tính toàn vẹn và resume session")
    s_res.add_argument("--sid", help="Session ID")

    # 2. intent & model
    p_int = sub.add_parser("intent", help="Phân loại mode & đánh giá rủi ro")
    p_int.add_argument("text", nargs="+", help="Mô tả yêu cầu của người dùng")
    p_int.add_argument("--path", dest="paths", action="append", help="Đường dẫn file dự kiến tác động")

    p_mod = sub.add_parser("model", help="Gợi ý model Gemini (Hydrogen / Neon / Carbon) theo role & độ phức tạp")
    p_mod.add_argument("--role", required=True, help="Tên role/stage")
    p_mod.add_argument("--high-risk", action="store_true")
    p_mod.add_argument("--complex", action="store_true")
    p_mod.add_argument("--repeated-failure", action="store_true")

    # 3. scan
    p_scan = sub.add_parser("scan", help="Quét ngôn ngữ, framework và công cụ kiểm thử của dự án")
    p_scan.add_argument("path", nargs="?", default=".")
    p_scan.add_argument("--sid")
    p_scan.add_argument("--no-cache", action="store_true")

    # 4. repomap
    p_rm = sub.add_parser("repomap", help="Sinh và truy vấn bản đồ module (WHERE)")
    p_rm.add_argument("--root", default=".")
    p_rm.add_argument("--out")
    p_rm.add_argument("--limit", type=int, default=5)
    p_rm.add_argument("--no-cache", action="store_true")
    p_rm.add_argument("--query", dest="query_text", help="Từ khóa truy vấn nhanh")
    rm_sub = p_rm.add_subparsers(dest="repomap_action")
    rm_build = rm_sub.add_parser("build", help="Sinh/làm mới chỉ mục repomap")
    rm_build.add_argument("--root", default=".")
    rm_build.add_argument("--out")
    rm_build.add_argument("--no-cache", action="store_true")
    rm_q = rm_sub.add_parser("query", help="Truy vấn top-N module")
    rm_q.add_argument("keyword", nargs="+")
    rm_q.add_argument("--root", default=".")
    rm_q.add_argument("--out")
    rm_q.add_argument("--limit", type=int, default=5)

    # 5. catalog & capabilities
    p_cat = sub.add_parser("catalog", help="Chỉ mục commands, flows, roles, rules & Antigravity skills")
    p_cat.add_argument("--no-cache", action="store_true")
    sub.add_parser("capabilities", help="Hiển thị capability & mức cưỡng chế trên Antigravity IDE")

    # 6. scaffold & handoff
    p_scaf = sub.add_parser("scaffold", help="Tạo file handoff mẫu cho một stage")
    p_scaf.add_argument("--sid", required=True)
    p_scaf.add_argument("--stage", required=True)
    p_scaf.add_argument("--slug", default="task")
    p_scaf.add_argument("--overwrite", action="store_true")

    p_ho = sub.add_parser("handoff", help="Thao tác với Handoff Contract")
    ho_sub = p_ho.add_subparsers(dest="handoff_action")
    ho_val = ho_sub.add_parser("validate", help="Kiểm tra sâu Handoff Contract")
    ho_val.add_argument("--sid", required=True)
    ho_val.add_argument("--stage", required=True)

    # 7. state
    p_st = sub.add_parser("state", help="Đọc hoặc chuyển trạng thái stage")
    st_sub = p_st.add_subparsers(dest="state_action")
    st_get = st_sub.add_parser("get")
    st_get.add_argument("--sid")
    st_tr = st_sub.add_parser("transition")
    st_tr.add_argument("--sid", required=True)
    st_tr.add_argument("--stage", required=True)
    st_tr.add_argument("--status", required=True)
    st_tr.add_argument("--expected-revision", type=int)
    st_tr.add_argument("--reason")
    st_tr.add_argument("--command-name")
    st_tr.add_argument("--new-hypothesis", action="store_true")
    st_cmp = st_sub.add_parser("complete", help="Hoàn tất nhanh 1 stage (tự running -> validate -> approved nếu auto-pass hoặc awaiting_approval nếu cần HITL)")
    st_cmp.add_argument("--sid", required=True)
    st_cmp.add_argument("--stage", required=True)
    st_uow = st_sub.add_parser("uow", help="Đăng ký hoặc hoàn tất UoW có kiểm tra xung đột vùng ghi")
    st_uow.add_argument("--sid", required=True)
    st_uow.add_argument("--uow-id", required=True)
    st_uow.add_argument("--stage")
    st_uow.add_argument("--objective")
    st_uow.add_argument("--write-path", action="append")
    st_uow.add_argument("--status", dest="uow_status", choices=["running", "completed", "failed"], default="running")

    # 8. gate
    p_gate = sub.add_parser("gate", help="Ghi nhận quyết định của con người tại Stage Gate")
    gate_sub = p_gate.add_subparsers(dest="gate_action")
    for act in ("approve", "reject", "abort"):
        g_p = gate_sub.add_parser(act)
        g_p.add_argument("--sid", required=True)
        g_p.add_argument("--stage", required=True)
        g_p.add_argument("--actor", required=True, help="Phải là 'human'")
        g_p.add_argument("--interaction-ref", required=True, help="Tham chiếu lần hỏi người dùng (vd: ask_question#1)")
        g_p.add_argument("--feedback")
        if act == "reject":
            g_p.add_argument("--return-to", help="Stage cần quay về (mặc định tự suy ra)")

    # 9. context & knowledge
    p_ctx = sub.add_parser("context", help="Chuẩn bị Context Packet & nén checkpoint tiết kiệm token")
    ctx_sub = p_ctx.add_subparsers(dest="context_action")
    ctx_prep = ctx_sub.add_parser("prepare")
    ctx_prep.add_argument("--sid", required=True)
    ctx_prep.add_argument("--stage", required=True)
    ctx_prep.add_argument("--query")
    ctx_cmp = ctx_sub.add_parser("compact")
    ctx_cmp.add_argument("--sid", required=True)

    p_kn = sub.add_parser("knowledge", help="Quản lý độ tươi mới tài liệu, Cross-Repo & Lessons Learned")
    kn_sub = p_kn.add_subparsers(dest="knowledge_action")
    kn_sub.add_parser("check-freshness", help="Kiểm tra các tài liệu bị cũ so với mã nguồn")
    kn_stamp = kn_sub.add_parser("stamp-ref", help="Sinh dòng source_ref kèm sha256 cho tài liệu")
    kn_stamp.add_argument("--source", required=True)
    kn_cr = kn_sub.add_parser("cross-repo", help="Truy vấn Cross-Repo Registry")
    kn_cr.add_argument("--query", nargs="+", required=True)
    kn_reg = kn_sub.add_parser("register-cross-repo", help="Đăng ký topic vào Cross-Repo Registry")
    kn_reg.add_argument("--repo-id", required=True)
    kn_reg.add_argument("--topic-id", required=True)
    kn_reg.add_argument("--path", required=True)
    kn_reg.add_argument("--description", default="")
    kn_reg.add_argument("--keyword", action="append")
    kn_reg.add_argument("--alias", action="append")
    kn_reg.add_argument("--local-path")
    kn_prop = kn_sub.add_parser("propose-lesson", help="Ghi bài học ở Lớp 3 chờ duyệt")
    kn_prop.add_argument("--sid", required=True)
    kn_prop.add_argument("--title", required=True)
    kn_prop.add_argument("--lesson", required=True)
    kn_prop.add_argument("--evidence-ref")
    kn_prom = kn_sub.add_parser("promote-lesson", help="Promote bài học lên Lớp 2 khi có human approval")
    kn_prom.add_argument("--sid", required=True)
    kn_prom.add_argument("--lesson-id", required=True)
    kn_prom.add_argument("--actor", required=True)
    kn_prom.add_argument("--interaction-ref", required=True)

    # 10. verify
    p_ver = sub.add_parser("verify", help="Lập kế hoạch & chạy kiểm chứng kèm chống Test Laundering")
    ver_sub = p_ver.add_subparsers(dest="verify_action")
    vp = ver_sub.add_parser("plan")
    vp.add_argument("--sid")
    vp.add_argument("--changed-path", action="append")
    vp.add_argument("--check", action="append", help="Override lệnh kiểm tra dạng layer=command")
    vr = ver_sub.add_parser("run")
    vr.add_argument("--sid")
    vr.add_argument("--check", action="append", help="Override lệnh kiểm tra dạng layer=command")
    vr.add_argument("--diff-file", help="File diff để kiểm tra Test Laundering")
    vr.add_argument("--approved-ac-change", action="store_true")
    vr.add_argument("--timeout", type=int, default=120)

    # 11. audit
    p_aud = sub.add_parser("audit", help="Quản lý Audit 4 lớp trung thực")
    aud_sub = p_aud.add_subparsers(dest="audit_action")
    a_st = aud_sub.add_parser("start")
    a_st.add_argument("--sid", required=True)
    a_st.add_argument("--slug")
    a_st.add_argument("--goal")
    a_st.add_argument("--mode", default="feature")
    a_st.add_argument("--policy", default="balanced")
    a_st.add_argument("--command-ref")
    a_st.add_argument("--prompt-ref")

    a_ev = aud_sub.add_parser("event")
    a_ev.add_argument("--audit-dir", required=True)
    a_ev.add_argument("--agent", required=True)
    a_ev.add_argument("--category", default="stage_event")
    a_ev.add_argument("--model")
    a_ev.add_argument("--summary")
    a_ev.add_argument("--human-wait-ms", type=int)
    a_ev.add_argument("--model-time-ms", type=int)
    a_ev.add_argument("--tool-time-ms", type=int)

    a_fin = aud_sub.add_parser("finalize")
    a_fin.add_argument("--audit-dir", required=True)
    a_fin.add_argument("--outcome", default="partial")
    a_fin.add_argument("--completion-level", default="claimed")
    a_fin.add_argument("--ac-passed", type=int, default=0)
    a_fin.add_argument("--ac-total", type=int, default=0)
    a_fin.add_argument("--build-status", default="not_available")
    a_fin.add_argument("--files-changed", type=int)
    a_fin.add_argument("--usage-json", help="JSON mảng số đo token xác thực (nếu có)")
    a_fin.add_argument("--usage-source", help="Tên nguồn đo xác thực")

    # 12. docs-view & audit-view (mặc định không mở trình duyệt trong CLI; thêm --open khi người dùng yêu cầu; giữ --no-open tương thích)
    p_dv = sub.add_parser("docs-view", help="Kết xuất bộ tài liệu Markdown thành HTML standalone")
    p_dv.add_argument("--docs-dir")
    p_dv.add_argument("--output")
    p_dv.add_argument("--open", action="store_true", help="Mở trình duyệt sau khi render")
    p_dv.add_argument("--no-open", action="store_true", help="Không mở trình duyệt (mặc định an toàn cho CI)")

    p_av = sub.add_parser("audit-view", help="Kết xuất dashboard Audit HTML theo tháng")
    p_av.add_argument("--month")
    p_av.add_argument("--audit-dir")
    p_av.add_argument("--output")
    p_av.add_argument("--open", action="store_true", help="Mở trình duyệt sau khi render")
    p_av.add_argument("--no-open", action="store_true", help="Không mở trình duyệt (mặc định an toàn cho CI)")

    # 13. cleanup
    p_cl = sub.add_parser("cleanup", help="Dry-run và dọn dẹp các artifact hoàn tất đã cũ")
    p_cl.add_argument("--older-than", type=int, default=30)
    p_cl.add_argument("--include-plans", action="store_true")
    p_cl.add_argument("--include-logs", action="store_true")
    p_cl.add_argument("--include-reports", action="store_true")
    p_cl.add_argument("--include-audit", action="store_true")
    p_cl.add_argument("--apply", action="store_true", help="Thực thi xóa thật (mặc định là dry-run)")

    # 14. benchmark
    p_bm = sub.add_parser("benchmark", help="Đo lường hiệu quả cắt giảm ngữ cảnh & đối chiếu paired benchmark")
    bm_sub = p_bm.add_subparsers(dest="benchmark_action")
    bm_s = bm_sub.add_parser("suite", help="Chạy benchmark routing & context funnel trên bộ task có oracle")
    bm_s.add_argument("--tasks-file", required=True, help="Đường dẫn file JSON chứa mảng tasks")
    bm_c = bm_sub.add_parser("compare", help="Đối chiếu paired giữa baseline và candidate")
    bm_c.add_argument("--baseline", required=True)
    bm_c.add_argument("--candidate", required=True)

    # 15. update
    p_up = sub.add_parser("update", help="Cập nhật hoặc rollback Speedy an toàn qua Ownership Manifest")
    p_up.add_argument("--source", help="Đường dẫn gói cục bộ hoặc URL Git repository")
    p_up.add_argument("--ref", help="Tag hoặc nhánh Git cụ thể (mặc định ưu tiên tag speedy-v* mới nhất, fallback nhánh mặc định)")
    p_up.add_argument("--apply", action="store_true", help="Áp dụng cập nhật thật (mặc định là dry-run)")
    p_up.add_argument("--skip-conflicts", action="store_true", help="Giữ nguyên các file dự án đang xung đột")
    p_up.add_argument("--force-overwrite", action="store_true", help="Ghi đè cả file đã tùy chỉnh (vẫn có backup)")
    p_up.add_argument("--rollback", help="Đường dẫn thư mục backup cần khôi phục")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 1

    dispatch = {
        "session": _handle_session,
        "intent": _handle_intent,
        "model": _handle_model,
        "scan": _handle_scan,
        "repomap": _handle_repomap,
        "catalog": _handle_catalog,
        "capabilities": _handle_capabilities,
        "scaffold": _handle_scaffold,
        "handoff": _handle_handoff,
        "state": _handle_state,
        "gate": _handle_gate,
        "context": _handle_context,
        "knowledge": _handle_knowledge,
        "verify": _handle_verify,
        "audit": _handle_audit,
        "docs-view": _handle_docs_view,
        "audit-view": _handle_audit_view,
        "cleanup": _handle_cleanup,
        "benchmark": _handle_benchmark,
        "update": _handle_update,
    }

    try:
        layout = resolve_layout(args.workspace, layout_mode=args.layout)
        return dispatch[args.command](layout, args)
    except SpeedyError as err:
        return _emit_err(err)
    except Exception as exc:  # pragma: no cover - bẫy lỗi bất ngờ thành JSON diagnostic chuẩn
        unexpected = SpeedyError(ErrorCode.INVALID_INPUT, f"Lỗi không mong đợi: {exc}", exit_code=1)
        return _emit_err(unexpected)


if __name__ == "__main__":
    sys.exit(main())
