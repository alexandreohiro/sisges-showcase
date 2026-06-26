def nome_guerra_fallback(nome_completo: str) -> str:
    partes = [p for p in nome_completo.strip().split() if p]
    if not partes:
        return ""
    return partes[-1].upper()