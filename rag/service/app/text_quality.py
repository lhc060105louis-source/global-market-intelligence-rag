"""Small, conservative checks for text that is unsafe to index.

The ingestion API receives decoded JSON strings, so a malformed byte sequence
can otherwise arrive as the Unicode replacement character (``U+FFFD``) or as
a field full of question marks.  Keeping the check in one module lets the
ingestion path and retrieval-text generator apply the same rule without
silently repairing evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class TextQualityIssue:
    """A machine-readable quality issue found in a text value."""

    path: str
    code: str
    message: str


class TextQualityError(ValueError):
    """Raised when text must not be persisted or sent to an index."""

    def __init__(self, issues: list[TextQualityIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(issue.message for issue in issues[:3])
        if len(issues) > 3:
            summary += f"; and {len(issues) - 3} more issue(s)"
        super().__init__(summary or "Text quality validation failed")


# A replacement character is never useful evidence.  These markers cover the
# common UTF-8-as-Windows-1252/Latin-1 mojibake prefixes without treating an
# ordinary accented word as corrupt unless several markers occur together.
_MOJIBAKE_MARKERS = frozenset("ÃÂÐÑæçèåêëï¿")


def _iter_text_values(value: Any, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _iter_text_values(item, child)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_text_values(item, f"{path}[{index}]")


def _inspect_text(path: str, value: str) -> list[TextQualityIssue]:
    issues: list[TextQualityIssue] = []
    if "\ufffd" in value:
        issues.append(TextQualityIssue(
            path=path,
            code="unicode_replacement_character",
            message=f"{path} contains Unicode replacement character U+FFFD",
        ))

    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        issues.append(TextQualityIssue(
            path=path,
            code="invalid_unicode",
            message=f"{path} contains an invalid Unicode surrogate",
        ))

    meaningful_length = sum(not char.isspace() for char in value)
    question_marks = value.count("?")
    question_ratio = question_marks / max(meaningful_length, 1)
    # Two marks that make up at least half of a field, or three marks at a
    # lower ratio, are a useful boundary for common decode-corruption output.
    if question_marks >= 2 and (
        question_ratio >= 0.5 or (question_marks >= 3 and question_ratio >= 0.15)
    ):
        issues.append(TextQualityIssue(
            path=path,
            code="excessive_question_marks",
            message=(
                f"{path} contains excessive question marks "
                f"({question_marks}/{meaningful_length or 1}, "
                f"{question_ratio:.0%})"
            ),
        ))

    mojibake_markers = sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
    # A single mojibake letter can be legitimate in a foreign-language title;
    # require a run of suspicious characters before rejecting the field.
    if mojibake_markers >= 3 and mojibake_markers / max(meaningful_length, 1) >= 0.2:
        issues.append(TextQualityIssue(
            path=path,
            code="likely_mojibake",
            message=f"{path} looks like UTF-8 mojibake ({mojibake_markers} suspicious characters)",
        ))
    return issues


def find_text_quality_issues(value: Any, *, root: str = "payload") -> list[TextQualityIssue]:
    """Return all unsafe text issues in a JSON-compatible value."""

    issues: list[TextQualityIssue] = []
    for path, text in _iter_text_values(value, root):
        issues.extend(_inspect_text(path, text))
    return issues


def validate_text_quality(value: Any, *, root: str = "payload") -> None:
    """Raise :class:`TextQualityError` if ``value`` contains unsafe text."""

    issues = find_text_quality_issues(value, root=root)
    if issues:
        raise TextQualityError(issues)
