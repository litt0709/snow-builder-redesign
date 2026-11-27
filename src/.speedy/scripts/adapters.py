"""
adapters.py — Khai báo minh bạch khả năng và mức độ cưỡng chế (Enforcement Level) của Antigravity IDE.
Không giả lập capability nếu môi trường chưa bật hoặc chưa cung cấp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from contracts import EnforcementLevel, WorkspaceLayout


def get_antigravity_capabilities(layout: WorkspaceLayout) -> Dict[str, Any]:
    """Báo cáo trung thực các capability và mức cưỡng chế trên Antigravity IDE."""
    agents_dir = (layout.root / "src" / ".agents") if layout.kind == "builder" else (layout.root / ".agents")
    hooks_file = (layout.root / ".agents" / "hooks.json")
    hooks_enabled = hooks_file.is_file()

    return {
        "ide": "antigravity",
        "customization_root": agents_dir.relative_to(layout.root).as_posix() if agents_dir.exists() else ".agents",
        "capabilities": {
            "always_on_rules": {
                "supported": True,
                "enforcement_level": EnforcementLevel.ADVISORY.value,
                "location": "AGENTS.md + .agents/rules/00-core-invariants.md",
            },
            "progressive_skills": {
                "supported": True,
                "enforcement_level": EnforcementLevel.ADVISORY.value,
                "location": ".agents/skills/*/SKILL.md",
            },
            "hitl_approval_ui": {
                "supported": True,
                "tool_name": "ask_question",
                "fallback": "chat_explicit_confirmation",
                "enforcement_level": EnforcementLevel.WORKFLOW_ENFORCED.value,
            },
            "independent_subagent_review": {
                "supported": True,
                "tool_name": "invoke_subagent",
                "fallback": "sequential_roles",
                "enforcement_level": EnforcementLevel.WORKFLOW_ENFORCED.value,
            },
            "pre_tool_use_hooks": {
                "supported": True,
                "active_in_workspace": hooks_enabled,
                "enforcement_level": (
                    EnforcementLevel.RUNTIME_ENFORCED.value
                    if hooks_enabled
                    else EnforcementLevel.ADVISORY.value
                ),
            },
            "realtime_token_telemetry": {
                "supported": False,
                "status": "unsupported_without_explicit_caller_metrics",
                "fallback": "null / source=not_measured",
            },
        },
        "model_priority": [
            {"tier": 1, "model": "Gemini Hydrogen", "use_for": "orchestrator, docs-manager, writer"},
            {"tier": 2, "model": "Gemini Neon", "use_for": "analyst, implementer, tester (mặc định)"},
            {"tier": 3, "model": "Gemini Carbon", "use_for": "chỉ bài toán cực khó / rủi ro cao (hạn chế quota)"},
        ],
    }
