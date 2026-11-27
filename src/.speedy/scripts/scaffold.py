"""
scaffold.py — Khởi tạo template chuẩn cho Handoff Contract, Plan, Root Cause và Verify Report.
Đảm bảo có sẵn đủ 5 headings bắt buộc + khối Resume Metadata để Agent chỉ cần điền dữ liệu thực.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict

from contracts import ErrorCode, STAGE_FILES, STAGE_LABELS, SpeedyError, WorkspaceLayout, sanitize_slug, validate_sid
from handoff import normalize_stage_id
from storage import atomic_write_text, session_dir_for

_STAGE_TEMPLATES: Dict[str, str] = {
    "root_cause": """# Root Cause Pre-flight — {slug}

- **SID**: `{sid}`
- **Date**: `{date}`

## Summary
[FILL — mô tả hiện tượng lỗi và điều kiện tái hiện]

## Scope
- **IN scope**:
  - [FILL — module/file gây lỗi]
- **OUT of scope**:
  - Không refactor ngoài vùng gây lỗi.

## Risks
- [FILL — nguy cơ ảnh hưởng luồng liền kề]

## Dependencies
- [FILL — dữ liệu mẫu hoặc môi trường cần để tái hiện]

## Open questions
Không có

## Root Cause Analysis
- **Vị trí phát sinh**: [FILL — `path:line`]
- **Cách tái hiện (Fail-to-Pass)**: [FILL — lệnh chạy tái hiện lỗi]
- **Nguyên nhân gốc rễ**: [FILL]

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "root_cause",
  "revision": 1,
  "input_refs": [],
  "next_action": "Chuyển sang Analyst lập Implementation Brief dựa trên nguyên nhân gốc.",
  "verification_refs": []
}}
```
""",
    "analyst": """# Handoff 1 — Analyst: {slug}

- **SID**: `{sid}`
- **Date**: `{date}`
- **Agent**: Analyst

## Summary
[FILL — tóm tắt yêu cầu nghiệp vụ và bài toán cần giải quyết]

## Scope
- **IN scope**:
  - [FILL — danh sách module/file dự kiến tác động]
- **OUT of scope**:
  - [FILL — các phần không làm để tránh scope creep]

## Risks
| Rủi ro | Mức độ | Biện pháp giảm thiểu |
|---|---|---|
| [FILL] | Low/Medium/High | [FILL] |

## Dependencies
- [FILL — cấu hình, package hoặc stage phụ thuộc]

## Open questions
Không có

## Acceptance Criteria
| Mã AC | Điều kiện nghiệm thu có thể kiểm chứng | Cách kiểm tra |
|---|---|---|
| AC-001 | [FILL — mô tả hành vi mong đợi] | [FILL — unit/integration test] |

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "analyst",
  "revision": 1,
  "input_refs": [],
  "next_action": "Chờ User duyệt Brief; sau đó chuyển sang Architect thiết kế chi tiết.",
  "verification_refs": []
}}
```
""",
    "architect": """# Handoff 2 — Architect: {slug}

- **SID**: `{sid}`
- **Date**: `{date}`
- **Agent**: Architect

## Summary
[FILL — tóm tắt giải pháp kiến trúc đã chọn]

## Scope
- **IN scope**:
  - [FILL — các file sẽ tạo mới hoặc chỉnh sửa]
- **OUT of scope**:
  - [FILL]

## Risks
- [FILL — đánh đổi hiệu năng, tương thích ngược và phương án rollback]

## Dependencies
- Input đã duyệt: `handoff-1-analyst.md`

## Open questions
Không có

## Alternatives Matrix
| Phương án | Ưu điểm | Nhược điểm | Độ phức tạp |
|---|---|---|---|
| Phương án A (Chọn) | [FILL] | [FILL] | Thấp/Vừa |
| Phương án B | [FILL] | [FILL] | Cao |

## ADR
- **Quyết định**: [FILL — phương án cam kết triển khai]
- **Lý do**: [FILL — căn cứ kỹ thuật và KISS/SOLID]

## Interface & Action Plan
1. [FILL — chữ ký hàm/class, kiểu dữ liệu, xử lý lỗi]

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "architect",
  "revision": 1,
  "input_refs": ["{session_rel}/handoff-1-analyst.md"],
  "next_action": "Chờ User duyệt thiết kế; sau đó chuyển sang Implementer viết code.",
  "verification_refs": []
}}
```
""",
    "implementer": """# Handoff 3 — Implementer: {slug}

- **SID**: `{sid}`
- **Date**: `{date}`
- **Agent**: Implementer

## Summary
[FILL — tóm tắt thay đổi mã nguồn đã thực hiện theo thiết kế]

## Scope
- **IN scope**:
  - [FILL — đường dẫn các file thực tế đã tạo/sửa]
- **OUT of scope**:
  - Không thay đổi ngoài thiết kế đã duyệt.

## Risks
- [FILL — các điểm cần Reviewer và Tester chú ý kiểm tra]

## Dependencies
- Thiết kế đầu vào: `handoff-2-architect.md`

## Open questions
Không có

## Files Modified & Local Checks
| File | Thao tác | Ghi chú |
|---|---|---|
| [FILL] | Create/Edit | [FILL] |

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "implementer",
  "revision": 1,
  "input_refs": ["{session_rel}/handoff-2-architect.md"],
  "next_action": "Chuyển sang Reviewer kiểm tra độc lập.",
  "verification_refs": []
}}
```
""",
    "reviewer": """# Handoff 4 — Reviewer: {slug}

- **SID**: `{sid}`
- **Date**: `{date}`
- **Agent**: Reviewer

## Summary
- **Verdict**: `APPROVE`
- [FILL — nhận xét tổng quan đối chiếu với AC và ADR]

## Scope
- Đã rà soát các file thay đổi từ `handoff-3-implementer.md`.

## Risks
- [FILL — rủi ro bảo mật, regression hoặc biên dữ liệu]

## Dependencies
- Đối chiếu với `handoff-1-analyst.md`, `handoff-2-architect.md`, `handoff-3-implementer.md`.

## Open questions
Không có

## Issues & Evidence
| Mức độ | File:Line | Mô tả & Bằng chứng | Hướng xử lý |
|---|---|---|---|
| None | - | Không phát hiện vi phạm spec hay test laundering | - |

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "reviewer",
  "revision": 1,
  "input_refs": [
    "{session_rel}/handoff-1-analyst.md",
    "{session_rel}/handoff-2-architect.md",
    "{session_rel}/handoff-3-implementer.md"
  ],
  "next_action": "Chờ User duyệt kết quả Review; nếu APPROVE chuyển sang Tester.",
  "verification_refs": []
}}
```
""",
    "tester": """# Handoff 5 — Tester: {slug}

- **SID**: `{sid}`
- **Date**: `{date}`
- **Agent**: Tester

## Summary
[FILL — tổng hợp kết quả kiểm thử và độ phủ AC]

## Scope
- Các file kiểm thử trong `tests/` phủ kín thay đổi từ `handoff-3-implementer.md`.

## Risks
- [FILL — giới hạn môi trường kiểm thử nếu có]

## Dependencies
- Tiêu chí gốc từ `handoff-1-analyst.md`.

## Open questions
Không có

## AC Coverage Matrix
| Mã AC | Test / Lệnh thực thi | Kết quả | Bằng chứng |
|---|---|---|---|
| AC-001 | [FILL] | PASS | [FILL] |

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "tester",
  "revision": 1,
  "input_refs": [
    "{session_rel}/handoff-1-analyst.md",
    "{session_rel}/handoff-3-implementer.md"
  ],
  "next_action": "Chờ User duyệt kết quả kiểm thử; sau đó chuyển sang Docs Manager.",
  "verification_refs": []
}}
```
""",
    "docs": """# Handoff 6 — Docs Manager: {slug}

- **SID**: `{sid}`
- **Date**: `{date}`
- **Agent**: Docs Manager

## Summary
[FILL — tóm tắt các tài liệu đã đồng bộ hoặc lý do không cần cập nhật]

## Scope
- Đồng bộ tài liệu liên quan trong vùng docs được phép.

## Risks
- Không có rủi ro thay đổi hành vi runtime.

## Dependencies
- Dựa trên thay đổi thực tế từ `handoff-3-implementer.md`.

## Open questions
Không có

## Docs Updated
| Tài liệu | Trạng thái | Tóm tắt cập nhật |
|---|---|---|
| [FILL] | Updated / Unchanged | [FILL] |

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "docs",
  "revision": 1,
  "input_refs": ["{session_rel}/handoff-3-implementer.md"],
  "next_action": "Chờ User duyệt đồng bộ tài liệu để hoàn tất Wrap-up.",
  "verification_refs": []
}}
```
""",
    "verify_report": """# Verify Report — {slug}

- **SID**: `{sid}`
- **Date**: `{date}`

## Summary
- **Kết luận**: `PASS`
- [FILL — tóm tắt kết quả xác minh độc lập]

## Scope
- [FILL — vùng mã nguồn đã kiểm tra, không sửa đổi code]

## Risks
- [FILL]

## Dependencies
- [FILL]

## Open questions
Không có

## Kết quả Đối chiếu Yêu cầu
| Mã AC / Yêu cầu | Trạng thái | Bằng chứng |
|---|---|---|
| AC-001 | PASS | [FILL] |

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "verify_report",
  "revision": 1,
  "input_refs": [],
  "next_action": "Chờ User xác nhận báo cáo Verify.",
  "verification_refs": []
}}
```
""",
}


def scaffold_handoff(
    layout: WorkspaceLayout,
    sid: str,
    stage: str | int | float,
    *,
    slug: str = "task",
    overwrite: bool = False,
) -> Dict[str, object]:
    validate_sid(sid)
    stage_id = normalize_stage_id(stage)
    if stage_id not in _STAGE_TEMPLATES:
        raise SpeedyError(ErrorCode.INVALID_INPUT, f"Stage '{stage_id}' không có mẫu scaffold.")

    sdir = session_dir_for(layout, sid)
    sdir.mkdir(parents=True, exist_ok=True)
    file_path = sdir / STAGE_FILES[stage_id]
    session_rel = sdir.relative_to(layout.root).as_posix()

    already_existed = file_path.exists()
    if not already_existed or overwrite:
        rendered = _STAGE_TEMPLATES[stage_id].format(
            sid=sid,
            slug=sanitize_slug(slug),
            date=datetime.now().strftime("%Y-%m-%d"),
            session_rel=session_rel,
        )
        atomic_write_text(file_path, rendered)

    return {
        "sid": sid,
        "stage": stage_id,
        "agent": STAGE_LABELS.get(stage_id, stage_id),
        "file_path": file_path.relative_to(layout.root).as_posix(),
        "created": not already_existed or overwrite,
        "existed_already": already_existed and not overwrite,
    }


def scaffold_plan(layout: WorkspaceLayout, sid: str, slug: str, goal: str) -> Path:
    date_prefix = sid[:10]
    safe_slug = sanitize_slug(slug)
    layout.plans_dir.mkdir(parents=True, exist_ok=True)
    candidate = layout.plans_dir / f"{date_prefix}-{safe_slug}.md"
    # Tránh ghi đè nếu trong ngày đã có một plan cùng tên thuộc session khác
    if candidate.exists():
        existing_text = candidate.read_text(encoding="utf-8", errors="ignore")
        if sid not in existing_text:
            candidate = layout.plans_dir / f"{date_prefix}-{safe_slug}-{sid[-6:]}.md"

    if not candidate.exists():
        content = f"""# Plan: {goal}

- **SID**: `{sid}`
- **Created**: `{date_prefix}`
- **Status**: `in_progress`

## Mục tiêu
{goal}

## Các bước thực hiện
- [ ] Phân tích yêu cầu & khóa AC (`analyst`)
- [ ] Thiết kế giải pháp & ADR (`architect`)
- [ ] Triển khai mã nguồn trong scope (`implementer`)
- [ ] Review độc lập & kiểm thử (`reviewer` + `tester`)
- [ ] Đồng bộ tài liệu & tổng kết (`docs` + `wrapup`)
"""
        atomic_write_text(candidate, content)
    return candidate
