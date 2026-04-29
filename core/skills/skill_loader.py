"""
SkillLoader — reads SKILL.md files from hermes_home/skills/*/
and injects relevant skill context into Hermes prompts.
"""
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("SkillLoader")

SKILLS_DIR = Path(__file__).parents[2] / "hermes_home" / "skills"

# Max chars to include per skill in an injection block
_MAX_SKILL_CHARS = 1200


class SkillLoader:
    def __init__(self, skills_dir: Optional[Path] = None):
        self._dir = Path(skills_dir) if skills_dir else SKILLS_DIR
        self._skills: List[Dict] = []
        self._load()

    def _load(self):
        loaded = 0
        for skill_dir in sorted(self._dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_md.exists():
                continue
            try:
                content = skill_md.read_text(encoding="utf-8")
                name = skill_dir.name
                keywords = self._extract_keywords(name, content)
                domain = self._extract_domain(content)
                self._skills.append({
                    "name": name,
                    "domain": domain,
                    "keywords": keywords,
                    "content": content,
                })
                loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load skill {skill_dir.name}: {e}")
        logger.info(f"[SKILLS] Loaded {loaded} skills from {self._dir}")

    def _extract_keywords(self, name: str, content: str) -> List[str]:
        """Derive trigger keywords from TRIGGER KEYWORDS section, directory name, and headings."""
        parts = re.split(r"[_\-\s]+", name.lower())

        # Primary: parse ## TRIGGER KEYWORDS section (comma-separated phrases)
        tk_match = re.search(
            r"##\s+TRIGGER\s+KEYWORDS\s*\n(.*?)(?=##|\Z)", content, re.DOTALL | re.IGNORECASE
        )
        if tk_match:
            tk_text = tk_match.group(1).strip()
            # Split by commas, strip whitespace
            for phrase in tk_text.split(","):
                phrase = phrase.strip().lower()
                if phrase:
                    parts.append(phrase)  # keep full phrases for better matching

        # Also pull words from the first H1/H2 heading in the file
        heading_match = re.search(r"^##? .+", content, re.MULTILINE)
        if heading_match:
            heading_words = re.split(r"\W+", heading_match.group().lower())
            parts += [w for w in heading_words if len(w) > 3]

        # Deduplicate, strip stopwords
        stopwords = {
            "the", "and", "for", "with", "from", "this", "that",
            "skill", "version", "description", "core", "rules",
        }
        return list({w for w in parts if w and w not in stopwords})

    def _extract_domain(self, content: str) -> str:
        """Extract the Domain field from a SKILL.md."""
        domain_match = re.search(r"##\s+Domain:\s*(.+)", content, re.IGNORECASE)
        if domain_match:
            return domain_match.group(1).strip()
        # Fallback: use first heading after title
        heading_match = re.search(r"^# (.+)", content, re.MULTILINE)
        return heading_match.group(1).strip() if heading_match else ""

    def match(self, text: str, max_skills: int = 3) -> List[Dict]:
        """Return skills whose keywords appear in text. Max 3 to keep tokens tight."""
        text_lower = text.lower()
        scored = []
        for skill in self._skills:
            hits = sum(1 for kw in skill["keywords"] if kw in text_lower)
            if hits > 0:
                scored.append((hits, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:max_skills]]

    def format_for_injection(self, skills: List[Dict]) -> str:
        """Format matched skills into a compact block for Hermes system prompt."""
        if not skills:
            return ""
        blocks = []
        for skill in skills:
            content = skill["content"]
            # Extract the most useful sections: DESCRIPTION + FIX VOCABULARY + EXAMPLE PROMPTS
            sections = self._extract_sections(content)
            trimmed = "\n".join(sections)[:_MAX_SKILL_CHARS]
            blocks.append(f"[SKILL: {skill['name']}]\n{trimmed}")
        return "\n\n".join(blocks)

    def _extract_sections(self, content: str) -> List[str]:
        """Pull out the highest-value sections from a SKILL.md."""
        priority_headers = [
            "DESCRIPTION", "FIX VOCABULARY", "EXAMPLE PROMPTS",
            "CORE RULES", "PROMPT ARCHITECTURE", "ADVANCED TECHNIQUES",
            "VOCABULARY", "STYLE VOCABULARY", "SIGNATURE ELEMENTS",
        ]
        lines = content.splitlines()
        result = []
        current_section = []
        capturing = False

        for line in lines:
            header_match = re.match(r"^#{1,3}\s+(.+)", line)
            if header_match:
                header_text = header_match.group(1).strip().upper()
                is_priority = any(p in header_text for p in priority_headers)
                if capturing and current_section:
                    result.extend(current_section)
                    current_section = []
                capturing = is_priority
            if capturing:
                current_section.append(line)

        if capturing and current_section:
            result.extend(current_section)

        # If nothing matched, return first 40 lines as fallback
        return result if result else lines[:40]

    def reload(self):
        self._skills = []
        self._load()

    @property
    def skill_names(self) -> List[str]:
        return [s["name"] for s in self._skills]

    def list_skills(self) -> List[Dict]:
        """Return all loaded skills with name, domain, and keyword count for API listing."""
        return [
            {
                "name": s["name"],
                "domain": s.get("domain", ""),
                "keywords": s["keywords"],
                "keyword_count": len(s["keywords"]),
            }
            for s in self._skills
        ]

    def get_skills_context(self, text: str, max_skills: int = 3) -> str:
        """Match skills against text and return formatted context block for system prompt injection."""
        matched = self.match(text, max_skills=max_skills)
        return self.format_for_injection(matched)
