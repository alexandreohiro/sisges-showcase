from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any


DATE_FIELDS = {
    "data_nascimento",
    "data_falecimento",
    "data_praca",
    "apresentacao_om",
    "apresentacao_gu",
    "data_incorporacao",
    "data_engajamento",
    "data_reengajamento",
    "data_desengajamento",
    "data_licenciamento",
    "data_exclusao_servico_ativo",
    "data_turma",
    "ultima_promocao",
}

FIELD_ALIASES = {
    "om": "om",
    "posto": "posto_graduacao",
    "posto/graduacao": "posto_graduacao",
    "posto/graduação": "posto_graduacao",
    "posto graduacao": "posto_graduacao",
    "posto graduação": "posto_graduacao",
    "situacao militar": "situacao_militar",
    "situação militar": "situacao_militar",
    "situacao regulamentar": "situacao_regulamentar",
    "situação regulamentar": "situacao_regulamentar",
    "nome completo": "nome_completo",
    "nome de guerra": "nome_guerra",
    "identidade": "identidade",
    "identidade civil": "identidade_civil",
    "cpf": "cpf",
    "cp": "cp",
    "prec-cp": "prec_cp",
    "prec cp": "prec_cp",
    "pis/pasep": "pis_pasep",
    "pis pasep": "pis_pasep",
    "cnh": "cnh",
    "titulo": "titulo_numero",
    "título": "titulo_numero",
    "titulo/zona/secao": "titulo_numero",
    "titulo/zona/seção": "titulo_numero",
    "título/zona/seção": "titulo_numero",
    "data nascimento": "data_nascimento",
    "local nascimento": "local_nascimento",
    "nome do pai": "nome_pai",
    "nome da mae": "nome_mae",
    "nome da mãe": "nome_mae",
    "estado civil": "estado_civil",
    "sexo": "sexo",
    "escolaridade": "escolaridade",
    "nacionalidade": "nacionalidade",
    "categoria": "categoria",
    "ra": "ra",
    "tipo sanguineo": "tipo_sanguineo",
    "tipo sanguíneo": "tipo_sanguineo",
    "fator rh": "fator_rh",
    "religiao": "religiao",
    "religião": "religiao",
    "data de praca": "data_praca",
    "data de praça": "data_praca",
    "apresentacao na om": "apresentacao_om",
    "apresentação na om": "apresentacao_om",
    "apresentacao na gu": "apresentacao_gu",
    "apresentação na gu": "apresentacao_gu",
    "ultima promocao": "ultima_promocao",
    "última promoção": "ultima_promocao",
    "secao": "secao",
    "seção": "secao",
    "funcao": "funcao",
    "função": "funcao",
    "endereco": "endereco",
    "endereço": "endereco",
    "ramal": "ramal",
    "telefone": "telefone",
    "celular": "celular",
    "contato de emergencia": "contato_emergencia",
    "contato de emergência": "contato_emergencia",
    "email": "email",
    "e-mail": "email",
    "e mail": "email",
    "status": "status_servico",
    "status servico": "status_servico",
    "status serviço": "status_servico",
    "qas/qms": "qas_qms",
    "rm": "rm",
    "local om": "local_om",
    "comportamento": "comportamento",
    "observacoes": "observacoes",
    "observações": "observacoes",
}

PERIODO_FIELD_ALIASES = {
    "tipo_registro": "tipo_registro",
    "tipo registro": "tipo_registro",
    "tipo": "subtipo_registro",
    "subtipo_registro": "subtipo_registro",
    "subtipo registro": "subtipo_registro",
    "subtipo": "subtipo_registro",
    "natureza_servico": "natureza_servico",
    "natureza serviço": "natureza_servico",
    "natureza servico": "natureza_servico",
    "natureza": "natureza_servico",
    "categoria_tempo": "categoria_tempo",
    "categoria tempo": "categoria_tempo",
    "categoria": "categoria_tempo",
    "origem": "origem",
    "data_inicio": "data_inicio",
    "data início": "data_inicio",
    "data inicial": "data_inicio",
    "inicio": "data_inicio",
    "início": "data_inicio",
    "data_fim": "data_fim",
    "data fim": "data_fim",
    "data final": "data_fim",
    "fim": "data_fim",
    "computa_tempo": "computa_tempo",
    "computa tempo": "computa_tempo",
    "arregimentado": "arregimentado",
    "dias_lancados_override": "dias_lancados_override",
    "dias lançados override": "dias_lancados_override",
    "dias override": "dias_lancados_override",
    "documento_referencia": "documento_referencia",
    "documento referência": "documento_referencia",
    "documento referencia": "documento_referencia",
    "documento": "documento_referencia",
    "status_calculo": "status_calculo",
    "status cálculo": "status_calculo",
    "status calculo": "status_calculo",
    "om_origem": "om_origem",
    "om origem": "om_origem",
    "origem om": "om_origem",
    "om_destino": "om_destino",
    "om destino": "om_destino",
    "destino om": "om_destino",
    "descricao": "descricao",
    "descrição": "descricao",
    "observacoes": "observacoes",
    "observações": "observacoes",
}

PERIODO_BLOCK_TYPE_ALIASES = {
    "movimentacao": "movimentacao",
    "movimentação": "movimentacao",
    "servico anterior": "servico_anterior",
    "serviço anterior": "servico_anterior",
    "acrescimo": "acrescimo_tempo",
    "acréscimo": "acrescimo_tempo",
    "acrescimo tempo": "acrescimo_tempo",
    "acréscimo tempo": "acrescimo_tempo",
    "tempo de servico": "tempo_servico",
    "tempo de serviço": "tempo_servico",
    "afastamento": "afastamento",
    "marco funcional": "marco_funcional",
}

BOOLEAN_FIELDS = {"computa_tempo", "arregimentado"}
INTEGER_FIELDS = {"dias_lancados_override"}


def _normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _normalize_value(value: str) -> str:
    return value.strip().replace("–", "-").replace("—", "-")


def _parse_br_date(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None

    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def _parse_bool(value: str) -> bool | None:
    normalized = _normalize_key(value)
    if normalized in {"true", "1", "sim", "yes", "y"}:
        return True
    if normalized in {"false", "0", "nao", "não", "no", "n"}:
        return False
    return None


def _parse_posto_block(value: str) -> dict[str, Any]:
    value = _normalize_value(value)
    match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", value)
    if match:
        return {
            "posto_graduacao": match.group(1).strip() or None,
            "situacao_militar": match.group(2).strip() or None,
        }
    return {"posto_graduacao": value or None}


def _parse_titulo_zona_secao(value: str) -> dict[str, Any]:
    parts = [part.strip() for part in value.split("/")]

    result: dict[str, Any] = {}
    if len(parts) >= 1:
        result["titulo_numero"] = parts[0] or None
    if len(parts) >= 2:
        result["titulo_zona"] = parts[1] or None
    if len(parts) >= 3:
        result["titulo_secao"] = parts[2] or None
    return result


def _parse_data_local_nascimento(value: str) -> dict[str, Any]:
    parts = [part.strip() for part in value.split("/")]

    if len(parts) >= 4:
        data_raw = "/".join(parts[:3]).strip()
        local_raw = "/".join(parts[3:]).strip()
    elif len(parts) >= 2:
        data_raw = parts[0]
        local_raw = "/".join(parts[1:]).strip()
    else:
        return {}

    result: dict[str, Any] = {}
    parsed_date = _parse_br_date(data_raw)
    if parsed_date:
        result["data_nascimento"] = parsed_date
    if local_raw:
        result["local_nascimento"] = local_raw
    return result


def parse_militar_text(raw_text: str) -> dict[str, Any]:
    parsed_data: dict[str, Any] = {"ativo": True}
    warnings: list[str] = []
    unmapped_lines: list[str] = []

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            continue

        if ":" not in line:
            unmapped_lines.append(line)
            continue

        raw_key, raw_value = line.split(":", 1)
        key = _normalize_key(raw_key)
        value = _normalize_value(raw_value)

        if not value:
            continue

        if key == "posto":
            parsed_data.update(_parse_posto_block(value))
            continue

        if key in {"titulo/zona/secao", "titulo/zona/seção", "título/zona/seção"}:
            parsed_data.update(_parse_titulo_zona_secao(value))
            continue

        if key in {"data / local nascimento", "data/local nascimento"}:
            parsed_data.update(_parse_data_local_nascimento(value))
            continue

        mapped_field = FIELD_ALIASES.get(key)
        if not mapped_field:
            continue

        if mapped_field in DATE_FIELDS:
            parsed_date = _parse_br_date(value)
            if parsed_date:
                parsed_data[mapped_field] = parsed_date
            else:
                warnings.append(f"Data não reconhecida para '{raw_key}': {value}")
            continue

        parsed_data[mapped_field] = value

    if not parsed_data.get("nome_completo"):
        warnings.append("Nome completo não foi encontrado no texto.")

    return {
        "parsed_data": parsed_data,
        "warnings": warnings,
        "unmapped_lines": unmapped_lines,
    }


def _split_full_blocks(raw_text: str) -> list[str]:
    blocks = [block.strip() for block in raw_text.split("---")]
    return [block for block in blocks if block]


def _first_nonempty_line(block: str) -> str:
    for line in block.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def _infer_periodo_tipo_from_block(block: str) -> str | None:
    first_line = _first_nonempty_line(block)
    if not first_line:
        return None

    if ":" in first_line:
        raw_key, raw_value = first_line.split(":", 1)
        normalized_key = _normalize_key(raw_key)
        normalized_value = _normalize_key(raw_value)

        if normalized_key in {"tipo_registro", "tipo registro"}:
            return normalized_value.replace(" ", "_") or None

        if normalized_key in PERIODO_BLOCK_TYPE_ALIASES:
            return PERIODO_BLOCK_TYPE_ALIASES[normalized_key]

        if normalized_value in PERIODO_BLOCK_TYPE_ALIASES:
            return PERIODO_BLOCK_TYPE_ALIASES[normalized_value]

    normalized_first = _normalize_key(first_line.rstrip(":"))
    return PERIODO_BLOCK_TYPE_ALIASES.get(normalized_first)


def _looks_like_periodo_block(block: str) -> bool:
    if _infer_periodo_tipo_from_block(block):
        return True

    normalized = _normalize_key(block)
    return "tipo_registro:" in normalized or "tipo registro:" in normalized


def parse_periodos_text(raw_text: str) -> dict[str, Any]:
    warnings: list[str] = []
    unmapped_lines: list[str] = []
    parsed_periodos: list[dict[str, Any]] = []

    blocks = _split_full_blocks(raw_text)

    for block in blocks:
        if not _looks_like_periodo_block(block):
            continue

        item: dict[str, Any] = {}
        local_unmapped: list[str] = []

        inferred_tipo = _infer_periodo_tipo_from_block(block)
        if inferred_tipo:
            item["tipo_registro"] = inferred_tipo

        lines = [line.strip() for line in block.splitlines() if line.strip()]
        start_index = 0

        if lines:
            first_line = lines[0]
            if first_line.endswith(":") and _normalize_key(first_line[:-1]) in PERIODO_BLOCK_TYPE_ALIASES:
                start_index = 1
            elif ":" in first_line:
                raw_key, _ = first_line.split(":", 1)
                if _normalize_key(raw_key) in PERIODO_BLOCK_TYPE_ALIASES:
                    start_index = 1

        for raw_line in lines[start_index:]:
            if ":" not in raw_line:
                local_unmapped.append(raw_line)
                continue

            raw_key, raw_value = raw_line.split(":", 1)
            key = _normalize_key(raw_key)
            value = _normalize_value(raw_value)

            mapped_field = PERIODO_FIELD_ALIASES.get(key)
            if not mapped_field:
                local_unmapped.append(raw_line)
                continue

            if mapped_field in {"data_inicio", "data_fim"}:
                parsed_date = _parse_br_date(value)
                if parsed_date:
                    item[mapped_field] = parsed_date
                else:
                    warnings.append(f"Data inválida no período para '{raw_key}': {value}")
                continue

            if mapped_field in BOOLEAN_FIELDS:
                parsed_bool = _parse_bool(value)
                if parsed_bool is None:
                    warnings.append(f"Booleano inválido no período para '{raw_key}': {value}")
                else:
                    item[mapped_field] = parsed_bool
                continue

            if mapped_field in INTEGER_FIELDS:
                try:
                    item[mapped_field] = int(value)
                except ValueError:
                    warnings.append(f"Inteiro inválido no período para '{raw_key}': {value}")
                continue

            item[mapped_field] = value

        if item.get("tipo_registro"):
            item.setdefault("categoria_tempo", "computado")
            item.setdefault("origem", "importacao_texto")
            item.setdefault("computa_tempo", True)
            item.setdefault("arregimentado", False)
            item.setdefault("status_calculo", "pendente")
            parsed_periodos.append(item)

        unmapped_lines.extend(local_unmapped)

    return {
        "parsed_periodos": parsed_periodos,
        "warnings": warnings,
        "unmapped_lines": unmapped_lines,
    }


def parse_full_import_text(raw_text: str) -> dict[str, Any]:
    militar_result = parse_militar_text(raw_text)
    periodos_result = parse_periodos_text(raw_text)

    return {
        "parsed_data": militar_result["parsed_data"],
        "parsed_periodos": periodos_result["parsed_periodos"],
        "warnings": [
            *militar_result["warnings"],
            *periodos_result["warnings"],
        ],
        "unmapped_lines": [
            *militar_result["unmapped_lines"],
            *periodos_result["unmapped_lines"],
        ],
    }