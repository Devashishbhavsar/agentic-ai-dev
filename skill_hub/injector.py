"""
SkillInjector — enriches agent system prompts with relevant skill snippets at runtime.

Instead of every agent knowing about skills upfront, the injector pulls the right
skills from the registry and appends their instructions to the agent's system prompt.
This keeps agent files clean while making skills composable and swappable.
"""
from __future__ import annotations

from functools import lru_cache

from skill_hub.registry import SkillRegistry, SkillMeta

# Singleton registry — loaded once, shared across all agents
@lru_cache(maxsize=1)
def _registry() -> SkillRegistry:
    return SkillRegistry()


class SkillInjector:
    """
    Enriches a system prompt with skill instructions pulled from the hub.

    Usage in an agent:
        injector = SkillInjector()
        enriched_prompt = injector.enrich(base_prompt, role="backend", tasks=["testing", "debugging"])
    """

    # How many chars of each skill to inject (keeps prompts tight)
    SNIPPET_CHARS = 500

    def __init__(self) -> None:
        self._reg = _registry()

    def enrich(
        self,
        base_prompt: str,
        role: str | None = None,
        tasks: list[str] | None = None,
        skill_names: list[str] | None = None,
        max_skills: int = 3,
    ) -> str:
        """
        Return base_prompt with relevant skill snippets appended.

        Priority: explicit skill_names > role lookup > task lookup.
        Deduplicates skills, caps at max_skills to avoid prompt bloat.
        """
        skills: list[SkillMeta] = []
        seen: set[str] = set()

        def _add(s: SkillMeta) -> None:
            if s.name not in seen and len(skills) < max_skills:
                seen.add(s.name)
                skills.append(s)

        # Explicit names first
        for name in (skill_names or []):
            s = self._reg.get(name)
            if s:
                _add(s)

        # Role-based skills
        for s in self._reg.get_for_role(role or ""):
            _add(s)

        # Task-based skills
        for task in (tasks or []):
            for s in self._reg.get_for_task(task):
                _add(s)

        if not skills:
            return base_prompt

        sections = [base_prompt.rstrip(), "\n\n## Active Skills\n"]
        for s in skills:
            sections.append(f"### {s.name}\n{s.snippet(self.SNIPPET_CHARS)}\n")

        return "\n".join(sections)

    def skills_for_display(
        self,
        role: str | None = None,
        tasks: list[str] | None = None,
    ) -> list[dict]:
        """Return a list of {name, description} dicts for display/logging."""
        result, seen = [], set()
        for s in self._reg.get_for_role(role or ""):
            if s.name not in seen:
                seen.add(s.name)
                result.append({"name": s.name, "description": s.description[:80]})
        for task in (tasks or []):
            for s in self._reg.get_for_task(task):
                if s.name not in seen:
                    seen.add(s.name)
                    result.append({"name": s.name, "description": s.description[:80]})
        return result


# Module-level convenience functions
def get_registry() -> SkillRegistry:
    return _registry()


def enrich_prompt(
    base_prompt: str,
    role: str | None = None,
    tasks: list[str] | None = None,
    skill_names: list[str] | None = None,
    max_skills: int = 3,
) -> str:
    """Module-level shortcut for SkillInjector.enrich()."""
    return SkillInjector().enrich(base_prompt, role=role, tasks=tasks,
                                  skill_names=skill_names, max_skills=max_skills)
