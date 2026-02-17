import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skill_manager import SkillManager


def _write_skill(root: Path, name: str, body: str):
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def test_detect_relevant_skills_by_keyword(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    _write_skill(
        skills_dir,
        "backend-api",
        """# Backend API\n\n## Metadata\n- Keywords: backend, api, database\n- Description: Backend API skill\n- Priority: 80\n\nUse FastAPI best practices.\n""",
    )

    sm = SkillManager(skills_directory=str(skills_dir))
    skills = sm.detect_relevant_skills("Build a backend API with database models")

    assert "backend-api" in skills


def test_get_skills_for_task_returns_formatted(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    _write_skill(
        skills_dir,
        "frontend-design",
        """# Frontend Design\n\n## Metadata\n- Keywords: frontend, ui, react\n- Description: Frontend UI skill\n- Priority: 70\n\nUse good UI patterns.\n""",
    )

    sm = SkillManager(skills_directory=str(skills_dir))
    formatted = sm.get_skills_for_task("Create a React UI")

    assert "RELEVANT SKILLS LOADED" in formatted
    assert "SKILL: FRONTEND-DESIGN" in formatted


def test_summarize_large_skill(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    long_body = "# Long Skill\n\n" + ("Rule: Always do X.\n" * 500)
    _write_skill(skills_dir, "long-skill", long_body)

    sm = SkillManager(skills_directory=str(skills_dir))
    summary = sm.get_skill_content("long-skill", summarize=True, max_tokens=50)

    assert "SKILL SUMMARY" in summary
    assert len(summary) > 0


def test_auto_detect_keywords(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    _write_skill(
        skills_dir,
        "react-skill",
        """# React Skill\n\nThis skill covers React components, JSX, and useState patterns.\n""",
    )

    sm = SkillManager(skills_directory=str(skills_dir))
    skills = sm.detect_relevant_skills("Build a React component")

    assert "react-skill" in skills
