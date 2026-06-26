import re


COMMON_REPLACEMENTS = {
    "AdministraMva": "Administrativa",
    "ConMnuação": "Continuação",
    "proûssional": "profissional",
    "ûlho": "filho",
    "]sica": "física",
    "di]ceis": "difíceis",
    "ParMcipou": "Participou",
    "conMnuou": "continuou",
    "seleMvo": "seletivo",
    "éMca": "ética",
}


def validate_and_fix_text(text: str) -> tuple[str, list[str]]:
    diagnostics: list[str] = []
    fixed = text

    for wrong, correct in COMMON_REPLACEMENTS.items():
        if wrong in fixed:
            fixed = fixed.replace(wrong, correct)
            diagnostics.append(f"TEXT_FIX:{wrong}->{correct}")

    # ligaduras comuns
    ligatures = {
        "ﬁ": "fi",
        "ﬂ": "fl",
    }
    for wrong, correct in ligatures.items():
        if wrong in fixed:
            fixed = fixed.replace(wrong, correct)
            diagnostics.append(f"LIGATURE_FIX:{wrong}->{correct}")

    # normalização leve de espaços
    fixed = re.sub(r"[ \t]+", " ", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)

    return fixed.strip(), diagnostics