from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "for",
    "how",
    "i",
    "is",
    "it",
    "my",
    "of",
    "on",
    "not",
    "or",
    "problem",
    "problems",
    "issue",
    "issues",
    "the",
    "to",
    "too",
    "what",
    "working",
    "with",
}

_SECTION_HINTS: dict[str, set[str]] = {
    "camera": {"camera", "cameras"},
    "router": {"router", "routers", "home routers"},
    "wifi_modem": {"wifi", "wifi modem", "wi-fi modem", "modem", "modems", "gateway"},
    "cpu": {"cpu", "cpus", "processor", "processors"},
    "mobile_phone": {"phone", "phones", "mobile", "mobile phones"},
}

_NETWORK_TERMS = {"wifi", "wi", "fi", "internet", "network"}
_SUPPORTED_SECTION_KEYS = {"camera", "router", "wifi_modem", "cpu"}


def _normalize(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(token for token in tokens if token not in _STOPWORDS)


@dataclass(frozen=True)
class KnowledgeChunk:
    section: str
    text: str
    terms: set[str]
    section_key: str


@dataclass(frozen=True)
class KnowledgeMatch:
    section: str
    text: str
    score: int


class KnowledgeBaseService:
    def __init__(self, wiki_path: Path, min_score: int = 2) -> None:
        self.wiki_path = wiki_path
        self.min_score = min_score
        self._chunks: list[KnowledgeChunk] = []
        self.reload()

    def reload(self) -> None:
        if not self.wiki_path.exists():
            self._chunks = []
            return
        raw_text = self.wiki_path.read_text(encoding="utf-8")
        self._chunks = self._parse_chunks(raw_text)

    def search(self, query: str, preferred_section: str | None = None) -> KnowledgeMatch | None:
        query_terms = set(_normalize(query).split())
        if not query_terms:
            return None

        referenced_sections = _detect_referenced_sections(query_terms)
        generic_network_issue = bool(query_terms.intersection(_NETWORK_TERMS)) and not referenced_sections
        preferred_key = (preferred_section or "").strip().lower()
        if preferred_key not in _SUPPORTED_SECTION_KEYS:
            preferred_key = ""

        best_score = 0
        best_chunk: KnowledgeChunk | None = None
        for chunk in self._chunks:
            if chunk.section_key not in _SUPPORTED_SECTION_KEYS:
                continue
            score = len(query_terms.intersection(chunk.terms))
            if referenced_sections:
                if chunk.section_key in referenced_sections:
                    score += 3
                else:
                    score -= 1
            elif generic_network_issue:
                if chunk.section_key == "router":
                    score += 2
                elif chunk.section_key == "wifi_modem":
                    score += 1
                elif chunk.section_key == "camera":
                    score -= 1
            if preferred_key:
                if chunk.section_key == preferred_key:
                    score += 4
                elif chunk.section_key in _SUPPORTED_SECTION_KEYS:
                    score -= 1
            if score > best_score:
                best_score = score
                best_chunk = chunk

        if best_chunk is None or best_score < self.min_score:
            return None

        return KnowledgeMatch(section=best_chunk.section, text=best_chunk.text, score=best_score)

    def _parse_chunks(self, raw_text: str) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        current_section = "General"
        section_lines: list[str] = []

        def flush_section() -> None:
            if not section_lines:
                return
            section_text = " ".join(line.strip() for line in section_lines if line.strip())
            section_lines.clear()
            if not section_text:
                return
            full_text = f"{current_section}: {section_text}"
            chunks.append(
                KnowledgeChunk(
                    section=current_section,
                    text=section_text,
                    terms=set(_normalize(full_text).split()),
                    section_key=_section_key(current_section),
                )
            )

        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if line.startswith("#"):
                flush_section()
                current_section = line.lstrip("#").strip() or "General"
                continue
            if not line:
                flush_section()
                continue
            section_lines.append(line)

        flush_section()
        return chunks


def _section_key(section_name: str) -> str:
    normalized = _normalize(section_name)
    tokens = set(normalized.split())
    for key, hints in _SECTION_HINTS.items():
        hint_tokens = set()
        for hint in hints:
            hint_tokens.update(_normalize(hint).split())
        if hint_tokens.intersection(tokens):
            return key
    return "general"


def _detect_referenced_sections(query_terms: set[str]) -> set[str]:
    matched: set[str] = set()
    for key, hints in _SECTION_HINTS.items():
        hint_tokens = set()
        for hint in hints:
            hint_tokens.update(_normalize(hint).split())
        if hint_tokens.intersection(query_terms):
            matched.add(key)
    return matched
