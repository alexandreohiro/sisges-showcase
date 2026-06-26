import re


NOISE_PATTERNS = [
    r"^\[\[SOURCE_FILE:.*\]\]$",
    r"^\[\[PAGE:\d+\]\]$",
    r"^BASE ADMINISTRATIVA DO QUARTEL-GENERAL DO EXÉRCITO.*FOLHA Nº.*$",
    r"^Continuação das Folhas de Alterações.*$",
    r"^MINISTÉRIO DA DEFESA$",
    r"^EXÉRCITO BRASILEIRO$",
    r"^SECRETARIA-GERAL DO EXÉRCITO$",
]


def clean_structural_noise(text: str) -> tuple[str, list[str]]:
    diagnostics: list[str] = []
    lines = text.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        should_skip = False
        for pattern in NOISE_PATTERNS:
            if re.match(pattern, stripped, flags=re.IGNORECASE):
                diagnostics.append(f"STRUCTURAL_REMOVED:{stripped[:80]}")
                should_skip = True
                break

        if should_skip:
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), diagnostics