"""
context.py — Xây dựng Context Packet đúng thông tin, đúng thời điểm (mục 3.8 & 3.10 specs/design.md),
kiểm tra độ tươi mới của tài liệu (Document Freshness), tra cứu Cross-Repo Registry,
nén checkpoint an toàn (Compaction) và quản lý đề xuất/phê duyệt Lessons Learned.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from contracts import STAGE_FILES, ErrorCode, SpeedyError, WorkspaceLayout, resolve_within_scope, validate_sid
from handoff import extract_acceptance_criteria, normalize_stage_id
from policy import select_gemini_model
from repomap import query_repomap
from storage import (
    atomic_write_json,
    atomic_write_text,
    file_sha256,
    load_session_state,
    read_json_safe,
    semantic_checksum,
    session_dir_for,
    session_lock,
    utc_now_iso,
)

CORE_INVARIANTS = [
    "Correctness-first: không bỏ gate, không hạ AC, không giảm kiểm thử bắt buộc.",
    "Minimal scope: chỉ sửa đúng đường dẫn được duyệt; phát hiện lỗi ngoài phạm vi thì ghi nhận vào Risks/Open questions.",
    "Evidence-first: không báo hoàn tất nếu chưa có bằng chứng kiểm thử thực tế; cấm sửa/skip test trái phép.",
]

_SOURCE_REF_LINE_RE = re.compile(
    r"^\s*[-*]\s*`?source_ref`?\s*:\s*`?([^|`\n]+)`?\s*\|\s*`?sha256`?\s*:\s*`?([a-fA-F0-9]{8,64})`?",
    re.MULTILINE,
)


def query_cross_repo_registry(layout: WorkspaceLayout, keyword: str) -> Dict[str, Any]:
    """Tra cứu registry.json trước, chỉ trả về con trỏ topic khớp từ khóa (không nạp toàn bộ docs ngoài)."""
    reg_path = layout.docs_dir / "cross-repo" / "registry.json"
    if not reg_path.is_file():
        return {"query": keyword, "count": 0, "matches": []}
    try:
        reg = read_json_safe(reg_path)
    except Exception:
        return {"query": keyword, "count": 0, "matches": []}

    kw_tokens = {t for t in re.split(r"[^a-z0-9]+", (keyword or "").lower()) if t}
    if not kw_tokens:
        return {"query": keyword, "count": 0, "matches": []}

    matches: List[Dict[str, Any]] = []
    for repo in reg.get("repos", []):
        if not isinstance(repo, dict):
            continue
        repo_id = str(repo.get("id", ""))
        aliases = [str(a).lower() for a in repo.get("aliases", [])]
        for topic in repo.get("topics", []):
            if not isinstance(topic, dict):
                continue
            topic_kws = {str(k).lower() for k in topic.get("keywords", [])}
            topic_kws |= set(re.split(r"[^a-z0-9]+", str(topic.get("id", "")).lower()))
            topic_kws |= set(re.split(r"[^a-z0-9]+", repo_id.lower())) | set(aliases)
            overlap = kw_tokens & topic_kws
            if overlap:
                rel_doc = f"cross-repo/{topic.get('path', '')}".lstrip("/")
                doc_abs = layout.docs_dir / rel_doc
                matches.append(
                    {
                        "repo_id": repo_id,
                        "topic_id": topic.get("id"),
                        "matched_keywords": sorted(overlap),
                        "doc_path": doc_abs.relative_to(layout.root).as_posix() if doc_abs.exists() else rel_doc,
                        "exists": doc_abs.is_file(),
                        "updated_at": repo.get("updated_at"),
                    }
                )
    return {"query": keyword, "count": len(matches[:5]), "matches": matches[:5]}


def register_cross_repo_topic(
    layout: WorkspaceLayout,
    *,
    repo_id: str,
    description: str,
    topic_id: str,
    keywords: Sequence[str],
    topic_rel_path: str,
    aliases: Optional[Sequence[str]] = None,
    local_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Cập nhật an toàn `cross-repo/registry.json` theo schema chuẩn mục 3.8."""
    clean_repo = re.sub(r"[^a-z0-9_-]+", "-", repo_id.strip().lower()).strip("-")
    clean_topic = re.sub(r"[^a-z0-9_-]+", "-", topic_id.strip().lower()).strip("-")
    if not clean_repo or not clean_topic:
        raise SpeedyError(ErrorCode.INVALID_INPUT, "repo_id và topic_id không được rỗng.")

    reg_path = layout.docs_dir / "cross-repo" / "registry.json"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg: Dict[str, Any] = {"schema_version": 1, "repos": []}
    if reg_path.is_file():
        reg = read_json_safe(reg_path)

    repos: List[Dict[str, Any]] = reg.setdefault("repos", [])
    target_repo = next((r for r in repos if r.get("id") == clean_repo), None)
    today = datetime.now().strftime("%Y-%m-%d")
    if target_repo is None:
        target_repo = {
            "id": clean_repo,
            "aliases": list(aliases or []),
            "local_path": local_path,
            "description": description,
            "topics": [],
            "updated_at": today,
        }
        repos.append(target_repo)
    else:
        target_repo["description"] = description or target_repo.get("description", "")
        target_repo["updated_at"] = today
        if aliases:
            target_repo["aliases"] = sorted(set(target_repo.get("aliases", [])) | set(aliases))

    topics: List[Dict[str, Any]] = target_repo.setdefault("topics", [])
    norm_rel = topic_rel_path.lstrip("/")
    existing_topic = next((t for t in topics if t.get("id") == clean_topic), None)
    topic_obj = {
        "id": clean_topic,
        "keywords": sorted({k.strip().lower() for k in keywords if k.strip()}),
        "path": norm_rel,
    }
    if existing_topic is None:
        topics.append(topic_obj)
    else:
        existing_topic.update(topic_obj)

    atomic_write_json(reg_path, reg)
    return {
        "registry_path": reg_path.relative_to(layout.root).as_posix(),
        "repo_id": clean_repo,
        "topic": topic_obj,
    }


def stamp_source_ref_line(layout: WorkspaceLayout, source_rel_path: str) -> str:
    """Sinh dòng dấu vân tay nguồn `source_ref: <path> | sha256: <16hex>` để đính kèm vào tài liệu kiến trúc."""
    src_file = resolve_within_scope(layout.root, source_rel_path)
    if not src_file.is_file():
        raise SpeedyError(ErrorCode.NOT_FOUND, f"File nguồn không tồn tại: {source_rel_path}", path=source_rel_path)
    rel = src_file.relative_to(layout.root).as_posix()
    digest = file_sha256(src_file)[:16]
    return f"- `source_ref`: `{rel}` | `sha256`: `{digest}`"


def check_docs_freshness(layout: WorkspaceLayout) -> Dict[str, Any]:
    """
    Kiểm tra độ tươi mới của các tài liệu trong `docs/` có gắn `source_ref | sha256`:
    - Nếu file mã nguồn bị xóa hoặc nội dung đã đổi khác hash ghi trong tài liệu -> đánh dấu `stale`.
    """
    if not layout.docs_dir.is_dir():
        return {"fresh_count": 0, "stale_count": 0, "untracked_docs": 0, "stale_docs": []}

    fresh_docs: List[str] = []
    stale_docs: List[Dict[str, Any]] = []
    untracked = 0

    for md_path in sorted(layout.docs_dir.rglob("*.md")):
        if any(part.startswith(".") for part in md_path.relative_to(layout.docs_dir).parts):
            continue
        text = md_path.read_text(encoding="utf-8", errors="replace")
        refs = _SOURCE_REF_LINE_RE.findall(text)
        rel_doc = md_path.relative_to(layout.root).as_posix()
        if not refs:
            untracked += 1
            continue

        mismatches = []
        for src_rel_raw, expected_prefix in refs:
            src_rel = src_rel_raw.strip()
            try:
                src_abs = resolve_within_scope(layout.root, src_rel)
            except SpeedyError:
                mismatches.append({"source": src_rel, "reason": "out_of_scope"})
                continue
            if not src_abs.is_file():
                mismatches.append({"source": src_rel, "reason": "missing_source"})
                continue
            actual_hash = file_sha256(src_abs)
            if not actual_hash.startswith(expected_prefix.lower()):
                mismatches.append(
                    {
                        "source": src_rel,
                        "reason": "checksum_changed",
                        "expected_prefix": expected_prefix.lower(),
                        "actual_prefix": actual_hash[: len(expected_prefix)],
                    }
                )

        if mismatches:
            stale_docs.append({"doc_path": rel_doc, "mismatches": mismatches})
        else:
            fresh_docs.append(rel_doc)

    return {
        "fresh_count": len(fresh_docs),
        "stale_count": len(stale_docs),
        "untracked_docs": untracked,
        "fresh_docs": fresh_docs,
        "stale_docs": stale_docs,
    }


def propose_lesson(
    layout: WorkspaceLayout,
    *,
    sid: str,
    title: str,
    lesson: str,
    evidence_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Lưu bài học kinh nghiệm ở Lớp 3 (Session/Task Knowledge) chờ người dùng duyệt trước khi promote."""
    validate_sid(sid)
    sdir = session_dir_for(layout, sid)
    if not sdir.is_dir():
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Session '{sid}' không tồn tại.")

    lessons_path = sdir / "lessons.json"
    with session_lock(sdir, owner="lesson_propose"):
        data: Dict[str, Any] = {"sid": sid, "lessons": []}
        if lessons_path.is_file():
            data = read_json_safe(lessons_path)
        items: List[Dict[str, Any]] = data.setdefault("lessons", [])
        lesson_id = f"L-{len(items) + 1:03d}"
        entry = {
            "id": lesson_id,
            "title": title.strip(),
            "lesson": lesson.strip(),
            "evidence_ref": evidence_ref,
            "status": "proposed",
            "created_at": utc_now_iso(),
        }
        items.append(entry)
        atomic_write_json(lessons_path, data)
    return {"sid": sid, "lesson": entry, "lessons_path": lessons_path.relative_to(layout.root).as_posix()}


def promote_lesson_to_project(
    layout: WorkspaceLayout,
    *,
    sid: str,
    lesson_id: str,
    actor: str,
    interaction_ref: str,
) -> Dict[str, Any]:
    """
    Đưa bài học từ Lớp 3 lên Lớp 2 (`docs/development-rules/lessons-learned.md`).
    Trong chế độ `strict`, bắt buộc phải có phê duyệt của con người (`--actor human`).
    """
    validate_sid(sid)
    if actor.strip().lower() != "human" or not (interaction_ref or "").strip():
        raise SpeedyError(
            ErrorCode.GATE_REQUIRED,
            "Không tự động biến workaround thành quy tắc chung: bắt buộc '--actor human' và '--interaction-ref' để promote lesson.",
        )

    sdir = session_dir_for(layout, sid)
    lessons_path = sdir / "lessons.json"
    data = read_json_safe(lessons_path)
    target = next((item for item in data.get("lessons", []) if item.get("id") == lesson_id), None)
    if target is None:
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Không tìm thấy lesson '{lesson_id}' trong session '{sid}'.")

    target["status"] = "promoted"
    target["promoted_at"] = utc_now_iso()
    target["approved_by"] = interaction_ref.strip()
    atomic_write_json(lessons_path, data)

    dest_md = layout.docs_dir / "development-rules" / "lessons-learned.md"
    dest_md.parent.mkdir(parents=True, exist_ok=True)
    header = "# Bài Học Kinh Nghiệm Dự Án (Approved Lessons Learned)\n\n"
    existing = dest_md.read_text(encoding="utf-8") if dest_md.is_file() else header
    ev_line = f" (Evidence: `{target['evidence_ref']}`)" if target.get("evidence_ref") else ""
    block = f"- **[{sid} · {lesson_id}] {target['title']}**: {target['lesson']}{ev_line}\n"
    if block not in existing:
        atomic_write_text(dest_md, existing + block)

    return {
        "promoted": True,
        "sid": sid,
        "lesson_id": lesson_id,
        "target_doc": dest_md.relative_to(layout.root).as_posix(),
    }


def compact_session_checkpoint(layout: WorkspaceLayout, *, sid: str) -> Dict[str, Any]:
    """
    Nén ngữ cảnh phiên dài thành checkpoint cô đọng (`compacted-checkpoint.json`):
    Giữ 100% `goal`, `acceptance_criteria`, `approved_decisions`, `blocked_reason`, `failure_evidence` mới nhất và `next_action`;
    loại bỏ lịch sử lặp và tuyệt đối không lưu raw reasoning.
    """
    validate_sid(sid)
    state = load_session_state(layout, sid)
    sdir = session_dir_for(layout, sid)
    analyst_file = sdir / STAGE_FILES["analyst"]
    ac_list = (
        extract_acceptance_criteria(analyst_file.read_text(encoding="utf-8", errors="replace"))
        if analyst_file.is_file()
        else []
    )

    compacted = {
        "schema_version": 1,
        "sid": sid,
        "compacted_at": utc_now_iso(),
        "goal": state.get("goal"),
        "mode": state.get("mode"),
        "policy": state.get("policy"),
        "current_stage": state.get("current_stage"),
        "status": state.get("status"),
        "uow_attempts": state.get("uow_attempts", 0),
        "acceptance_criteria": ac_list,
        "approved_decisions": state.get("approvals", {}),
        "blocked_reason": state.get("blocked_reason"),
        "latest_failure": (state.get("failure_history") or [])[-1] if state.get("failure_history") else None,
        "next_action": state.get("next_action"),
    }
    out_path = sdir / "compacted-checkpoint.json"
    atomic_write_json(out_path, compacted)
    return {
        "checkpoint_path": out_path.relative_to(layout.root).as_posix(),
        "checkpoint": compacted,
    }


def _extract_open_assumptions(markdown_text: str) -> List[str]:
    assumptions: List[str] = []
    for line in markdown_text.splitlines():
        stripped = line.strip(" -*\t")
        if not stripped:
            continue
        if any(tag in stripped.lower() for tag in ("[assumption]", "giả định:", "chưa xác minh")):
            assumptions.append(stripped[:240])
    return assumptions[:10]


def _extract_modified_code_refs(layout: WorkspaceLayout, implementer_md: str) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    seen = set()
    for token in re.findall(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`", implementer_md):
        if token in seen or token.endswith(".md") and "handoff-" in token:
            continue
        try:
            abs_p = resolve_within_scope(layout.root, token)
        except SpeedyError:
            continue
        if abs_p.is_file():
            seen.add(token)
            refs.append(
                {
                    "kind": "actual_source_file",
                    "path": abs_p.relative_to(layout.root).as_posix(),
                    "sha256_prefix": file_sha256(abs_p)[:16],
                    "reason": "Mã nguồn thực tế để Reviewer/Tester đối chiếu trực tiếp, không chỉ đọc tóm tắt.",
                }
            )
    return refs[:20]


def prepare_context_packet(
    layout: WorkspaceLayout,
    *,
    sid: str,
    stage: str | int | float,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Chuẩn bị Context Packet gọn nhẹ cho một role/stage:
    - Giữ nguyên vẹn `goal`, `acceptance_criteria`, `invariants`, `approved_decisions` và `failure_evidence`.
    - Với `reviewer` và `tester`: luôn cung cấp con trỏ tới các file mã nguồn thực tế trên đĩa (không chỉ summary).
    """
    validate_sid(sid)
    stage_id = normalize_stage_id(stage)
    state = load_session_state(layout, sid)
    budget_cfg = state.get("budget", {})
    max_packet_bytes = int(budget_cfg.get("max_context_packet_bytes", 16384))

    goal = str(state.get("goal", ""))
    search_kw = query or goal
    sdir = layout.sessions_dir / sid

    ac_list: List[str] = []
    open_assumptions: List[str] = []
    analyst_file = sdir / STAGE_FILES["analyst"]
    if analyst_file.is_file():
        analyst_md = analyst_file.read_text(encoding="utf-8", errors="replace")
        ac_list = extract_acceptance_criteria(analyst_md)
        open_assumptions.extend(_extract_open_assumptions(analyst_md))

    approved_decisions: List[Dict[str, Any]] = []
    input_refs: List[Dict[str, Any]] = []
    for st_key, app in state.get("approvals", {}).items():
        art_info = state.get("artifacts", {}).get(st_key, {})
        approved_decisions.append(
            {
                "stage": st_key,
                "path": art_info.get("path"),
                "revision": app.get("artifact_revision", 1),
                "semantic_checksum": app.get("artifact_checksum"),
                "approved_at": app.get("approved_at"),
            }
        )

    stage_inputs_map = {
        "analyst": ["root_cause"],
        "architect": ["analyst"],
        "implementer": ["analyst", "architect"],
        "reviewer": ["analyst", "architect", "implementer"],
        "tester": ["analyst", "implementer"],
        "docs": ["architect", "implementer"],
    }
    for needed_st in stage_inputs_map.get(stage_id, []):
        candidate_file = sdir / STAGE_FILES.get(needed_st, "")
        if candidate_file.is_file():
            txt = candidate_file.read_text(encoding="utf-8", errors="replace")
            input_refs.append(
                {
                    "kind": "stage_handoff",
                    "stage": needed_st,
                    "path": candidate_file.relative_to(layout.root).as_posix(),
                    "semantic_checksum": semantic_checksum(txt)[:16],
                    "reason": f"Đầu vào trực tiếp cho stage '{stage_id}'.",
                }
            )
            if needed_st == "implementer" and stage_id in {"reviewer", "tester"}:
                input_refs.extend(_extract_modified_code_refs(layout, txt))

    overview_doc = layout.docs_dir / "architecture" / "overview.md"
    if overview_doc.is_file():
        input_refs.append(
            {
                "kind": "knowledge_index",
                "path": overview_doc.relative_to(layout.root).as_posix(),
                "semantic_checksum": semantic_checksum(overview_doc.read_text(encoding="utf-8", errors="replace"))[:16],
                "reason": "Index kiến trúc nhẹ (WHAT) — đọc trước khi mở tài liệu module chi tiết.",
            }
        )

    arch_doc = layout.docs_dir / "architecture" / "architecture.md"
    if arch_doc.is_file():
        input_refs.append(
            {
                "kind": "architecture_doc",
                "path": arch_doc.relative_to(layout.root).as_posix(),
                "semantic_checksum": semantic_checksum(arch_doc.read_text(encoding="utf-8", errors="replace"))[:16],
                "reason": "Kiến trúc hệ thống cốt lõi (Tech Stack, Data Flow, Schema, API & ADR đã chốt).",
            }
        )

    if stage_id in {"architect", "implementer", "reviewer", "tester"}:
        for kind_name, rel_sub, desc in (
            (
                "coding_rules",
                Path("development-rules") / "coding-convention.md",
                "Quy ước lập trình chuẩn của dự án (Brownfield Repo Rules / Greenfield Principal Engineer Rules).",
            ),
            (
                "code_style",
                Path("development-style") / "STYLE.md",
                "Style Guide của dự án (ưu tiên Repo Style #1, Official Industry Style #2).",
            ),
        ):
            doc_path = layout.docs_dir / rel_sub
            if doc_path.is_file():
                input_refs.append(
                    {
                        "kind": kind_name,
                        "path": doc_path.relative_to(layout.root).as_posix(),
                        "semantic_checksum": semantic_checksum(doc_path.read_text(encoding="utf-8", errors="replace"))[:16],
                        "reason": desc,
                    }
                )

    repomap_res = query_repomap(layout, search_kw, limit=5)
    cross_repo_res = query_cross_repo_registry(layout, search_kw)

    failure_history = state.get("failure_history", [])
    recent_failures = failure_history[-2:] if failure_history else []
    latest_verify_fail = [
        v for v in state.get("verification", [])[-2:] if v.get("overall_status") == "FAIL"
    ]

    model_rec = select_gemini_model(
        stage_id,
        high_risk=bool(state.get("high_risk")),
        complex_architecture=bool(state.get("complex_architecture")),
        repeated_failure=int(state.get("uow_attempts", 0)) >= 2,
    )

    required_file = STAGE_FILES.get(stage_id)
    packet: Dict[str, Any] = {
        "schema_version": 1,
        "sid": sid,
        "stage": stage_id,
        "recommended_model": model_rec,
        "goal": goal,
        "acceptance_criteria": ac_list,
        "scope": state.get("scope", {}),
        "non_goals": [
            "Không tự ý mở rộng sang tính năng hoặc refactor ngoài scope đã duyệt.",
            "Không sửa test/assertion trái phép để vượt qua kiểm tra.",
        ],
        "invariants": CORE_INVARIANTS,
        "approved_decisions": approved_decisions,
        "repomap_matches": repomap_res.get("matches", []),
        "cross_repo_matches": cross_repo_res.get("matches", []),
        "input_refs": input_refs,
        "open_assumptions": open_assumptions,
        "failure_evidence": {
            "recent_stage_failures": recent_failures,
            "recent_verification_failures": latest_verify_fail,
        },
        "required_output": {
            "handoff_file": f"{sdir.relative_to(layout.root).as_posix()}/{required_file}" if required_file else None,
            "required_headings": [
                "## Summary",
                "## Scope",
                "## Risks",
                "## Dependencies",
                "## Open questions",
                "## Resume Metadata",
            ],
        },
        "stop_conditions": [
            "Dừng ngay sau khi xuất artifact và validate contract nếu chạy ở chế độ standalone hoặc strict gate.",
            f"Dừng báo blocker nếu chạm trần {budget_cfg.get('max_uow_attempts', 3)} attempts hoặc gặp lỗi ngoài scope.",
        ],
        "context_budget": {
            "max_packet_bytes": max_packet_bytes,
            "measurement": "utf8_bytes_proxy",
            "truncated_optional_refs": False,
        },
    }

    encoded = json.dumps(packet, ensure_ascii=False).encode("utf-8")
    if len(encoded) > max_packet_bytes and packet["repomap_matches"]:
        packet["repomap_matches"] = packet["repomap_matches"][:2]
        packet["context_budget"]["truncated_optional_refs"] = True
        encoded = json.dumps(packet, ensure_ascii=False).encode("utf-8")

    packet["context_budget"]["actual_packet_bytes"] = len(encoded)
    return packet
