"""Safe, local source-code knowledge for Gemini project questions.

The service intentionally excludes environment files, databases, build output,
dependencies, and other sensitive or binary content.  It sends small redacted
excerpts relevant to one question rather than uploading the whole workspace.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path


_ALLOWED_SUFFIXES = {".dart", ".py", ".md", ".yaml", ".yml", ".json"}
_IGNORED_DIRS = {
    ".git", ".dart_tool", ".idea", ".vscode", "build", "coverage",
    "node_modules", "venv", "__pycache__", "uploads",
}
_SENSITIVE_NAMES = {".env", ".env.example", "secrets", "credentials"}
_MAX_FILE_BYTES = 200_000
_REFRESH_SECONDS = 45
_MAX_EXCERPT_CHARS = 1_600
_MAX_CONTEXT_CHARS = 9_000
_SECRET_LINE = re.compile(
    r"(?im)^(\s*(?:[A-Z0-9_]*(?:KEY|TOKEN|PASSWORD|SECRET)|authorization)\s*[=:]\s*).+$"
)


@dataclass(frozen=True)
class _SourceDocument:
    relative_path: str
    content: str


class ProjectKnowledgeService:
    """Maintains a lightweight, redacted index of safe project text files."""

    def __init__(self) -> None:
        self._documents: list[_SourceDocument] = []
        self._last_refresh = 0.0

    @staticmethod
    def _workspace_root() -> Path:
        # .../Flutter/elder_care_backend/app/services/this_file.py -> .../Flutter
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _is_safe_file(path: Path) -> bool:
        if path.suffix.lower() not in _ALLOWED_SUFFIXES:
            return False
        if path.name.lower() in _SENSITIVE_NAMES or path.name.lower().startswith(".env"):
            return False
        return not any(part.lower() in _IGNORED_DIRS for part in path.parts)

    @staticmethod
    def _redact(text: str) -> str:
        return _SECRET_LINE.sub(r"\1[REDACTED]", text)

    def _refresh_if_needed(self) -> None:
        if self._documents and time.monotonic() - self._last_refresh < _REFRESH_SECONDS:
            return
        root = self._workspace_root()
        documents: list[_SourceDocument] = []
        for path in root.rglob("*"):
            if not path.is_file() or not self._is_safe_file(path):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if content.strip():
                documents.append(
                    _SourceDocument(
                        relative_path=path.relative_to(root).as_posix(),
                        content=self._redact(content),
                    )
                )
        self._documents = documents
        self._last_refresh = time.monotonic()

    @staticmethod
    def _keywords(query: str) -> list[str]:
        words = re.findall(r"[\w-]{3,}", query.casefold())
        ignored = {"about", "application", "feature", "please", "project", "what", "where", "with"}
        return [word for word in dict.fromkeys(words) if word not in ignored][:12]

    @staticmethod
    def _excerpt(content: str, keywords: list[str]) -> str:
        lower_content = content.casefold()
        positions = [lower_content.find(keyword) for keyword in keywords]
        position = next((item for item in positions if item >= 0), 0)
        start = max(0, position - 300)
        end = min(len(content), start + _MAX_EXCERPT_CHARS)
        return content[start:end]

    def context_for(self, query: str) -> dict[str, object]:
        """Return a bounded, relevant source excerpt set for a Gemini request."""
        self._refresh_if_needed()
        keywords = self._keywords(query)
        ranked: list[tuple[int, _SourceDocument]] = []
        for document in self._documents:
            text = f"{document.relative_path}\n{document.content}".casefold()
            score = sum(text.count(keyword) for keyword in keywords)
            if score:
                ranked.append((score, document))
        if not ranked:
            ranked = [(0, document) for document in self._documents if document.relative_path.endswith("README.md")]
        ranked.sort(key=lambda item: (-item[0], item[1].relative_path))

        excerpts: list[dict[str, str]] = []
        used = 0
        for _, document in ranked:
            excerpt = self._excerpt(document.content, keywords)
            if used + len(excerpt) > _MAX_CONTEXT_CHARS:
                break
            excerpts.append({"path": document.relative_path, "excerpt": excerpt})
            used += len(excerpt)
            if len(excerpts) >= 8:
                break
        return {
            "index_status": "safe project source index",
            "files_indexed": len(self._documents),
            "safety": "Environment files, secrets, databases, dependencies, and build output are excluded. Sensitive assignment lines are redacted.",
            "relevant_excerpts": excerpts,
        }


project_knowledge_service = ProjectKnowledgeService()
