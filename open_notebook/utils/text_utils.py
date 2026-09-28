"""
Text utilities for Open Notebook.
Extracted from main utils to avoid circular imports.
"""

import re
import unicodedata
from typing import Tuple

# Patterns for matching thinking content in AI responses
# Standard pattern: <think>...</think>
THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)
# Pattern for malformed output: content</think> (missing opening tag)
THINK_PATTERN_NO_OPEN = re.compile(r"^(.*?)</think>", re.DOTALL)


def remove_non_ascii(text: str) -> str:
    """Remove non-ASCII characters from text."""
    return re.sub(r"[^\x00-\x7F]+", "", text)


def remove_non_printable(text: str) -> str:
    """Remove non-printable characters from text."""
    # Replace any special Unicode whitespace characters with a regular space
    text = re.sub(r"[\u2000-\u200B\u202F\u205F\u3000]", " ", text)

    # Replace unusual line terminators with a single newline
    text = re.sub(r"[\u2028\u2029\r]", "\n", text)

    # Remove control characters, except newlines and tabs
    text = "".join(
        char for char in text if unicodedata.category(char)[0] != "C" or char in "\n\t"
    )

    # Replace non-breaking spaces with regular spaces
    text = text.replace("\xa0", " ").strip()

    # Keep letters (including accented ones), numbers, spaces, newlines, tabs, and basic punctuation
    return re.sub(r"[^\w\s.,!?\-\n\t]", "", text, flags=re.UNICODE)


def parse_thinking_content(content: str) -> Tuple[str, str]:
    """
    Parse message content to extract thinking content from <think> tags.

    Handles both well-formed tags and malformed output where the opening
    <think> tag is missing but </think> is present.

    Args:
        content (str): The original message content

    Returns:
        Tuple[str, str]: (thinking_content, cleaned_content)
            - thinking_content: Content from within <think> tags
            - cleaned_content: Original content with <think> blocks removed

    Example:
        >>> content = "<think>Let me analyze this</think>Here's my answer"
        >>> thinking, cleaned = parse_thinking_content(content)
        >>> print(thinking)
        "Let me analyze this"
        >>> print(cleaned)
        "Here's my answer"
    """
    # Input validation
    if not isinstance(content, str):
        return "", str(content) if content is not None else ""

    # Limit processing for very large content (100KB limit)
    if len(content) > 100000:
        return "", content

    # Find all well-formed thinking blocks
    thinking_matches = THINK_PATTERN.findall(content)

    if thinking_matches:
        # Join all thinking content with double newlines
        thinking_content = "\n\n".join(match.strip() for match in thinking_matches)

        # Remove all <think>...</think> blocks from the original content
        cleaned_content = THINK_PATTERN.sub("", content)

        # Clean up extra whitespace
        cleaned_content = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned_content).strip()

        return thinking_content, cleaned_content

    # Handle malformed output: content</think> (missing opening tag)
    # Some models like Nemotron output thinking without the opening <think> tag
    malformed_match = THINK_PATTERN_NO_OPEN.match(content)
    if malformed_match:
        thinking_content = malformed_match.group(1).strip()
        # Remove the thinking content and </think> tag
        cleaned_content = content[malformed_match.end() :].strip()
        return thinking_content, cleaned_content

    # Handle truncated output: <think>content (no closing tag). The model ran
    # out of output budget while still reasoning, so nothing is a real answer.
    stripped = content.lstrip()
    if stripped.startswith("<think>"):
        return stripped[len("<think>") :].strip(), ""

    return "", content


def clean_thinking_content(content: str) -> str:
    """
    Remove thinking content from AI responses, returning only the cleaned content.

    This is a convenience function for cases where you only need the cleaned
    content and don't need access to the thinking process.

    Args:
        content (str): The original message content with potential <think> tags

    Returns:
        str: Content with <think> blocks removed and whitespace cleaned

    Example:
        >>> content = "<think>Let me think...</think>Here's the answer"
        >>> clean_thinking_content(content)
        "Here's the answer"
    """
    _, cleaned_content = parse_thinking_content(content)
    return cleaned_content


def extract_text_content(content) -> str:
    """Extract text from LLM response content.

    Handles both plain string responses and structured content formats
    (e.g. Gemini's envelope format):
    [{'type': 'text', 'text': '...', 'extras': {...}}]

    Args:
        content: The content from an AI message, either a string or a list of parts.

    Returns:
        The extracted text content as a string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
            elif isinstance(part, str):
                text_parts.append(part)
        return "".join(text_parts)
    return str(content)


# Vietnamese letter families: every accented form of a base letter. Used to
# build accent-insensitive regexes that run inside SurrealDB (Rust regex), so
# "quy dinh" matches "Quy định" without a migration or an extra index.
_VI_LETTER_VARIANTS = {
    "a": "aàáảãạăằắẳẵặâầấẩẫậ",
    "d": "dđ",
    "e": "eèéẻẽẹêềếểễệ",
    "i": "iìíỉĩị",
    "o": "oòóỏõọôồốổỗộơờớởỡợ",
    "u": "uùúủũụưừứửữự",
    "y": "yỳýỷỹỵ",
}

# Characters with special meaning in Rust regex syntax; escaping them is
# always allowed there (unlike arbitrary escapes).
_REGEX_META = set("\\.+*?()|[]{}^$#&-~")


def fold_vietnamese(text: str) -> str:
    """Lowercase and strip Vietnamese diacritics ("Quy Định" -> "quy dinh")."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").lower()


def build_accent_insensitive_pattern(query: str) -> str | None:
    """Build a case- and accent-insensitive regex for a plain-text query.

    The query is trimmed, folded (diacritics stripped, lowercased) and each
    Vietnamese base letter is expanded to a class of all its accented forms,
    followed by ``\\p{M}*`` so text stored in decomposed (NFD) form matches
    too. A space in the query matches any run of whitespace, ``_``, ``.`` or
    ``-`` so "de an" also finds the file name "Đề_án.pdf". Returns ``None`` for an
    empty/blank query. The output targets Rust regex (SurrealDB
    ``string::matches``); everything else is escaped and matched literally.
    """
    folded = fold_vietnamese(query.strip())
    if not folded:
        return None

    parts: list[str] = []
    for word_index, word in enumerate(folded.split()):
        if word_index:
            parts.append(r"[\s_.\-]+")
        for ch in word:
            variants = _VI_LETTER_VARIANTS.get(ch)
            if variants:
                parts.append(f"[{variants}]" + r"\p{M}*")
            elif ch in _REGEX_META:
                parts.append("\\" + ch)
            else:
                parts.append(ch)
    return "(?i)" + "".join(parts)
