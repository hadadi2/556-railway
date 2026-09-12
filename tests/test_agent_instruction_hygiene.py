"""Regression guards for concise, task-scoped agent guidance."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_codex_guide_routes_context_instead_of_loading_everything() -> None:
    guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Do not read every" in guide
    assert "do not merge" in guide.lower()
    assert "Never fabricate data" in guide
    assert "docs/LIVE_PROOF_RUNBOOK.md" in guide


def test_claude_guide_has_no_blanket_pre_tool_read() -> None:
    guide = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "قبل أوّل نداء أداة في أي جلسة" not in guide
    assert "أول فعل في كل جلسة" not in guide
    assert "اقرأ ما يحتاجه الطلب" in guide


def test_skill_descriptions_stay_concise_and_specific() -> None:
    skill_files = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    assert skill_files

    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        assert match, f"{path}: missing one-line description"
        description = match.group(1).strip()
        assert len(description) <= 180, f"{path}: description is too broad/long"
        assert "ANY change" not in description
        assert "whenever planning" not in description
