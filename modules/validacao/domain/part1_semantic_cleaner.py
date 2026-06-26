import re


INVALID_STANDALONE_LINES = [
    r"^CP:\s*PERÍODO:.*$",
    r"^\d+º\s+Semestre\s+de\s+\d{4}.*$",
    r"^do\s+\d+º\s+Sgt\s+.*$",
    r"^do\s+2º\s+Sgt\s+.*$",
    r"^do\s+1º\s+Sgt\s+.*$",
    r"^do\s+Subtenente\s+.*$",
]

INLINE_NOISE_PATTERNS = [
    r"\bCP:\s*PERÍODO:\s*\d{2}/\d{2}/\d{4}\s*a\s*\d{2}/\d{2}/\d{4}\b",
    r"\b\d+º\s+Semestre\s+de\s+\d{4}\b",
]

BODY_START_NOISE = [
    r"^do\s+\d+º\s+Sgt\s+.+$",
    r"^do\s+Subtenente\s+.+$",
]


def clean_part1_semantics(text: str) -> tuple[str, list[str]]:
    diagnostics: list[str] = []
    lines = text.splitlines()
    cleaned_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            cleaned_lines.append("")
            continue

        should_drop = False

        for pattern in INVALID_STANDALONE_LINES:
            if re.match(pattern, line, flags=re.IGNORECASE):
                diagnostics.append(f"PART1_DROP_LINE:{line[:100]}")
                should_drop = True
                break

        if should_drop:
            continue

        cleaned_line = raw_line
        for pattern in INLINE_NOISE_PATTERNS:
            new_line = re.sub(pattern, "", cleaned_line, flags=re.IGNORECASE).strip()
            if new_line != cleaned_line.strip():
                diagnostics.append(f"PART1_INLINE_CLEAN:{line[:100]}")
                cleaned_line = new_line

        cleaned_lines.append(cleaned_line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), diagnostics


def is_invalid_part1_title(title: str) -> bool:
    title = (title or "").strip()
    if not title:
        return True

    invalid_patterns = [
        r"^CP:\s*PERÍODO:.*$",
        r"^\d+º\s+Semestre\s+de\s+\d{4}.*$",
        r"^PERÍODO:\s*.*$",
        r"^do\s+\d+º\s+Sgt\s+.*$",
        r"^do\s+Subtenente\s+.*$",
    ]

    return any(re.match(pattern, title, flags=re.IGNORECASE) for pattern in invalid_patterns)


def clean_part1_body_start(body: str) -> tuple[str, list[str]]:
    diagnostics: list[str] = []
    if not body:
        return body, diagnostics

    lines = body.splitlines()
    while lines:
        first = lines[0].strip()
        if not first:
            lines.pop(0)
            continue

        matched = False
        for pattern in BODY_START_NOISE:
            if re.match(pattern, first, flags=re.IGNORECASE):
                diagnostics.append(f"PART1_DROP_BODY_START:{first[:100]}")
                lines.pop(0)
                matched = True
                break
        if not matched:
            break

    cleaned = "\n".join(lines).strip()
    return cleaned, diagnostics