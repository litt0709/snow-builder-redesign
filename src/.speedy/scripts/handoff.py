"""
handoff.py — Deep Handoff Contract Validator.
Không chỉ kiểm tra tên heading mà còn phát hiện:
- Mục rỗng hoặc còn sót placeholder ([FILL], TODO, TBD).
- Thiếu hoặc sai khối JSON `## Resume Metadata` (sid, stage, revision, input_refs, next_action, verification_refs).
- Yêu cầu chuyên môn theo từng role (AC-xxx cho Analyst, ADR cho Architect, Verdict cho Reviewer, bảng AC cho Tester).
- Đường dẫn tham chiếu trong Scope vượt ra ngoài phạm vi được duyệt.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from contracts import (
    REQUIRED_HANDOFF_HEADINGS,
    STAGE_FILES,
    ErrorCode,
    SpeedyError,
    WorkspaceLayout,
    resolve_within_scope,
    validate_sid,
)
from storage import semantic_checksum, session_dir_for

_PLACEHOLDER_PATTERNS = (
    re.compile(r"\[FILL\b", re.IGNORECASE),
    re.compile(r"\bTODO\s*:", re.IGNORECASE),
    re.compile(r"\bTBD\b"),
    re.compile(r"<fill[-_a-z]*>", re.IGNORECASE),
)

_RESUME_META_KEYS = (
    "sid",
    "stage",
    "revision",
    "input_refs",
    "next_action",
    "verification_refs",
)

# Hộ trợ ánh xạ phase cũ (1, 2, 3, 3.5, 4, 5) sang stage định danh chuẩn để tương thích ngược
LEGACY_PHASE_TO_STAGE: Dict[str, str] = {
    "0.4": "root_cause",
    "1": "analyst",
    "2": "architect",
    "3": "implementer",
    "3.5": "reviewer",
    "4": "tester",
    "5": "docs",
}


def normalize_stage_id(stage_or_phase: str | int | float) -> str:
    raw = str(stage_or_phase).strip().lower()
    if raw in LEGACY_PHASE_TO_STAGE:
        return LEGACY_PHASE_TO_STAGE[raw]
    if raw in STAGE_FILES or raw in {"bootstrap", "wrapup"}:
        return raw
    raise SpeedyError(
        ErrorCode.INVALID_INPUT,
        f"Stage không được hỗ trợ: '{stage_or_phase}'.",
        remediation=f"Dùng một trong các định danh chuẩn: {sorted(STAGE_FILES.keys())}.",
    )


def _extract_h2_sections(markdown: str) -> Dict[str, str]:
    sections: Dict[str, List[str]] = {}
    current_heading: Optional[str] = None
    in_code_fence = False

    for line in markdown.replace("\r\n", "\n").splitlines():
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
        if not in_code_fence and line.startswith("## "):
            current_heading = "## " + line[3:].strip()
            sections.setdefault(current_heading, [])
            continue
        if current_heading is not None:
            sections[current_heading].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _parse_resume_metadata(section_body: str) -> tuple[Optional[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", section_body, re.DOTALL)
    raw_json = fence_match.group(1) if fence_match else section_body.strip()
    if not raw_json:
        return None, ["Mục '## Resume Metadata' bị rỗng."]
    try:
        meta = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, [f"JSON trong '## Resume Metadata' không hợp lệ: {exc}"]

    if not isinstance(meta, dict):
        return None, ["'## Resume Metadata' phải là một JSON object."]

    for key in _RESUME_META_KEYS:
        if key not in meta:
            errors.append(f"Thiếu khóa bắt buộc '{key}' trong Resume Metadata.")

    if "revision" in meta and (not isinstance(meta["revision"], int) or meta["revision"] < 1):
        errors.append("Trường 'revision' trong Resume Metadata phải là số nguyên >= 1.")
    if "input_refs" in meta and not isinstance(meta["input_refs"], list):
        errors.append("Trường 'input_refs' trong Resume Metadata phải là mảng chuỗi.")
    if "verification_refs" in meta and not isinstance(meta["verification_refs"], list):
        errors.append("Trường 'verification_refs' trong Resume Metadata phải là mảng chuỗi.")
    if "next_action" in meta and not str(meta["next_action"]).strip():
        errors.append("Trường 'next_action' trong Resume Metadata không được rỗng.")

    return meta, errors


_VERDICT_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*Verdict\*\*|Verdict)\s*:\s*`?(APPROVE_WITH_NOTES|REQUEST_CHANGES|APPROVE)`?(?:\s|$|[.,;])"
)


def extract_reviewer_verdict(content: str) -> Optional[str]:
    """Trích xuất verdict tường minh của Reviewer, tránh bị đánh lừa khi prose nhắc tới chữ 'APPROVE'."""
    explicit = _VERDICT_LINE_RE.findall(content or "")
    if explicit:
        # Ưu tiên verdict tường minh cuối cùng nếu có nhiều mục, nhưng nếu chứa REQUEST_CHANGES thì vẫn bắt chặt
        normalized = [v.upper() for v in explicit]
        if "REQUEST_CHANGES" in normalized:
            return "REQUEST_CHANGES"
        return normalized[-1]
    # Fallback bảo thủ khi không có dòng 'Verdict: ...': REQUEST_CHANGES luôn thắng
    if re.search(r"\bREQUEST_CHANGES\b", content or ""):
        return "REQUEST_CHANGES"
    m = re.search(r"\b(APPROVE_WITH_NOTES|APPROVE)\b", content or "")
    return m.group(1) if m else None


def _validate_role_specific_rules(stage: str, content: str) -> List[str]:
    issues: List[str] = []
    if stage == "analyst":
        if not re.search(r"\bAC[-_]?\d+\b", content):
            issues.append("Handoff của Analyst bắt buộc phải định nghĩa ít nhất một mã tiêu chí nghiệm thu (ví dụ: AC-001).")
    elif stage == "architect":
        if not re.search(r"^##+\s+ADR\b", content, re.MULTILINE | re.IGNORECASE):
            issues.append("Handoff của Architect bắt buộc phải có mục ADR ghi rõ quyết định kiến trúc.")
    elif stage == "reviewer":
        if extract_reviewer_verdict(content) is None:
            issues.append("Handoff của Reviewer bắt buộc phải nêu rõ Verdict: APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES.")
    elif stage == "tester":
        if not re.search(r"\bAC[-_]?\d+\b", content) or not re.search(r"\b(PASS|FAIL|PARTIAL)\b", content):
            issues.append("Handoff của Tester bắt buộc đối chiếu mã AC với kết quả chạy thực tế (PASS/FAIL/PARTIAL).")
    return issues


def extract_acceptance_criteria(analyst_markdown: str) -> List[str]:
    """Trích xuất danh sách dòng chứa AC-xxx từ handoff của Analyst để đưa vào Context Packet."""
    found: List[str] = []
    for line in analyst_markdown.splitlines():
        cleaned = line.strip()
        if re.search(r"\bAC[-_]?\d+\b", cleaned) and "[FILL" not in cleaned.upper():
            found.append(cleaned)
    return found


def validate_handoff(
    layout: WorkspaceLayout,
    sid: str,
    stage: str | int | float,
    *,
    allowed_paths: Optional[Sequence[str]] = None,
    forbidden_paths: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Kiểm tra toàn diện hợp đồng chuyển giao của một stage."""
    validate_sid(sid)
    stage_id = normalize_stage_id(stage)
    if stage_id not in STAGE_FILES:
        raise SpeedyError(ErrorCode.INVALID_INPUT, f"Stage '{stage_id}' không có file handoff riêng.")

    sdir = session_dir_for(layout, sid)
    file_path = sdir / STAGE_FILES[stage_id]
    rel_path = file_path.relative_to(layout.root).as_posix()

    if not file_path.is_file():
        return {
            "valid": False,
            "sid": sid,
            "stage": stage_id,
            "file_path": rel_path,
            "missing_headings": list(REQUIRED_HANDOFF_HEADINGS),
            "empty_headings": [],
            "placeholders": [],
            "errors": [f"Handoff file chưa tồn tại: {rel_path}"],
        }

    content = file_path.read_text(encoding="utf-8", errors="replace")
    sections = _extract_h2_sections(content)

    # Đối chiếu heading không phân biệt hoa thường ở phần chữ sau '## '
    lower_map = {h.lower(): (h, body) for h, body in sections.items()}
    missing_headings: List[str] = []
    empty_headings: List[str] = []

    for req in REQUIRED_HANDOFF_HEADINGS:
        matched = lower_map.get(req.lower())
        if matched is None:
            missing_headings.append(req)
        else:
            body_clean = re.sub(r"<!--.*?-->", "", matched[1], flags=re.DOTALL).strip(" -*\t\n")
            if not body_clean:
                empty_headings.append(req)

    placeholders: List[str] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(content):
            placeholders.append(match.group(0))

    errors: List[str] = []
    if missing_headings:
        errors.append(f"Thiếu các heading bắt buộc: {', '.join(missing_headings)}")
    if empty_headings:
        errors.append(f"Các heading bắt buộc đang bị bỏ trống: {', '.join(empty_headings)}")
    if placeholders:
        errors.append(f"Còn sót placeholder chưa điền nội dung thật: {sorted(set(placeholders))}")

    # Kiểm tra Resume Metadata (mục bổ sung thứ 6)
    resume_section = lower_map.get("## resume metadata")
    resume_meta: Optional[Dict[str, Any]] = None
    if resume_section is None:
        errors.append("Thiếu mục bắt buộc '## Resume Metadata' chứa JSON resume contract.")
    else:
        resume_meta, meta_errors = _parse_resume_metadata(resume_section[1])
        errors.extend(meta_errors)
        if resume_meta:
            if resume_meta.get("sid") != sid:
                errors.append(
                    f"Resume Metadata có sid='{resume_meta.get('sid')}' không khớp với session hiện tại '{sid}'."
                )
            if resume_meta.get("stage") and normalize_stage_id(str(resume_meta["stage"])) != stage_id:
                errors.append(
                    f"Resume Metadata có stage='{resume_meta.get('stage')}' không khớp với stage '{stage_id}'."
                )
            for ref in list(resume_meta.get("input_refs", [])) + list(resume_meta.get("verification_refs", [])):
                try:
                    resolve_within_scope(
                        layout.root,
                        str(ref),
                        forbidden_prefixes=forbidden_paths,
                    )
                except SpeedyError as exc:
                    errors.append(f"Đường dẫn tham chiếu không hợp lệ trong Resume Metadata ('{ref}'): {exc.message}")

    # Kiểm tra các đường dẫn backtick có dạng path trong mục IN Scope nếu có allowed_paths/forbidden_paths
    scope_entry = lower_map.get("## scope")
    if scope_entry and (allowed_paths or forbidden_paths):
        scope_body = scope_entry[1]
        in_scope_part = re.split(r"\*\*OUT of scope|\bOUT of scope|\bNgoài phạm vi", scope_body, maxsplit=1, flags=re.IGNORECASE)[0]
        for path_token in re.findall(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_./-]*)`", in_scope_part):
            if path_token.startswith(("http://", "https://")):
                continue
            try:
                resolve_within_scope(
                    layout.root,
                    path_token,
                    allowed_prefixes=allowed_paths,
                    forbidden_prefixes=forbidden_paths,
                )
            except SpeedyError as exc:
                errors.append(exc.message)

    errors.extend(_validate_role_specific_rules(stage_id, content))

    return {
        "valid": len(errors) == 0,
        "sid": sid,
        "stage": stage_id,
        "file_path": rel_path,
        "semantic_checksum": semantic_checksum(content),
        "revision": resume_meta.get("revision", 1) if isinstance(resume_meta, dict) else 1,
        "missing_headings": missing_headings,
        "empty_headings": empty_headings,
        "placeholders": sorted(set(placeholders)),
        "errors": errors,
    }
