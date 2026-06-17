"""
SkillHub Registry — indexes all installed skills and resolves them by role/task.

Agents call `registry.get_for_role(role)` or `registry.get_for_task(task)` to
get the full skill content to inject into their system prompt at runtime.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SKILLS_DIR = Path(__file__).parent.parent / ".agents" / "skills"
CATALOG_PATH = Path(__file__).parent / "catalog.json"


@dataclass
class SkillMeta:
    name: str
    description: str
    content: str          # full markdown content of SKILL.md
    tags: list[str] = field(default_factory=list)
    path: Path | None = None

    def snippet(self, max_chars: int = 600) -> str:
        """Return a compact excerpt — strips frontmatter, trims to max_chars."""
        body = re.sub(r"^---.*?---\s*", "", self.content, flags=re.DOTALL).strip()
        return body[:max_chars] + ("…" if len(body) > max_chars else "")


class SkillRegistry:
    """
    Central hub for all 33 installed skills.

    Usage:
        registry = SkillRegistry()
        skills = registry.get_for_role("backend")       # → list[SkillMeta]
        skills = registry.get_for_task("debugging")     # → list[SkillMeta]
        skill  = registry.get("systematic-debugging")   # → SkillMeta | None
        names  = registry.list_all()                    # → list[str]
        hits   = registry.search("verification")        # → list[SkillMeta]
    """

    def __init__(self) -> None:
        self._catalog: dict[str, Any] = json.loads(CATALOG_PATH.read_text())
        self._skills: dict[str, SkillMeta] = {}
        self._load_skills()

    # ─── Public API ────────────────────────────────────────────────────────

    def get(self, skill_name: str) -> SkillMeta | None:
        """Exact lookup by skill name."""
        return self._skills.get(skill_name)

    def get_for_role(self, role: str) -> list[SkillMeta]:
        """Return all skills relevant to an agent role (e.g. 'backend', 'qa')."""
        names = self._catalog["roles"].get(role, [])
        return [s for name in names if (s := self._skills.get(name)) is not None]

    def get_for_task(self, task: str) -> list[SkillMeta]:
        """Return all skills relevant to a task type (e.g. 'debugging', 'analytics')."""
        names = self._catalog["tasks"].get(task, [])
        return [s for name in names if (s := self._skills.get(name)) is not None]

    def get_for_swarm(self, swarm: str) -> list[SkillMeta]:
        """Return union of all skills used by every role in a swarm."""
        roles = self._catalog["swarms"].get(swarm, [])
        seen, result = set(), []
        for role in roles:
            for skill in self.get_for_role(role):
                if skill.name not in seen:
                    seen.add(skill.name)
                    result.append(skill)
        return result

    def list_all(self) -> list[str]:
        return sorted(self._skills.keys())

    def list_roles(self) -> list[str]:
        return sorted(self._catalog["roles"].keys())

    def list_tasks(self) -> list[str]:
        return sorted(self._catalog["tasks"].keys())

    def search(self, query: str) -> list[SkillMeta]:
        """Keyword search across skill names and descriptions."""
        q = query.lower()
        return [
            s for s in self._skills.values()
            if q in s.name or q in s.description.lower() or q in s.content.lower()
        ]

    def summary(self) -> dict:
        """Full catalog summary for display."""
        return {
            "total_skills": len(self._skills),
            "loaded": self.list_all(),
            "roles": list(self._catalog["roles"].keys()),
            "tasks": list(self._catalog["tasks"].keys()),
            "swarms": list(self._catalog["swarms"].keys()),
        }

    def role_card(self, role: str) -> dict:
        """Return a card showing which skills a role has and their descriptions."""
        skills = self.get_for_role(role)
        return {
            "role": role,
            "skill_count": len(skills),
            "skills": [{"name": s.name, "description": s.description[:80]} for s in skills],
        }

    def task_card(self, task: str) -> dict:
        skills = self.get_for_task(task)
        return {
            "task": task,
            "skill_count": len(skills),
            "skills": [{"name": s.name, "description": s.description[:80]} for s in skills],
        }

    # ─── Internal ──────────────────────────────────────────────────────────

    def _load_skills(self) -> None:
        """Scan .agents/skills/ and load every SKILL.md into memory."""
        if not SKILLS_DIR.exists():
            return
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                skill_file = skill_dir / "skill.md"
            if not skill_file.exists():
                # try any .md file
                mds = list(skill_dir.glob("*.md"))
                if not mds:
                    continue
                skill_file = mds[0]
            content = skill_file.read_text(errors="ignore")
            name, description = self._parse_frontmatter(content, skill_dir.name)
            self._skills[name] = SkillMeta(
                name=name,
                description=description,
                content=content,
                path=skill_file,
            )

    @staticmethod
    def _parse_frontmatter(content: str, fallback_name: str) -> tuple[str, str]:
        name, description = fallback_name, ""
        m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if m:
            front = m.group(1)
            n = re.search(r'^name:\s*(.+)$', front, re.MULTILINE)
            d = re.search(r'^description:\s*(.+)$', front, re.MULTILINE)
            if n:
                name = n.group(1).strip().strip('"')
            if d:
                description = d.group(1).strip().strip('"')
        return name, description
