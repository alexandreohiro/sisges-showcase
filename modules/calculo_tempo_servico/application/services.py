from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

from infra.persistence.models import (
    CalculoTempoServicoModel,
    LegislacaoModel,
    MilitarModel,
    MilitarPeriodoServicoModel,
)
from infra.persistence.transactions import atomic


@dataclass
class Duracao:
    anos: int
    meses: int
    dias: int
    total_dias: int


class CalculoTempoServicoConsolidador:
    """
    CALC.NORMA.4
    - preview
    - preview complementado
    - diff antes de aplicar respostas
    - aprovação assistida
    - persistência do snapshot
    """

    def __init__(self, db):
        self.db = db

    # =========================
    # utilitários
    # =========================
    def _normalize_days(self, total_dias: int) -> Duracao:
        anos = total_dias // 360
        resto = total_dias % 360
        meses = resto // 30
        dias = resto % 30
        return Duracao(anos=anos, meses=meses, dias=dias, total_dias=total_dias)

    def _ymd_to_days(self, anos: int, meses: int, dias: int) -> int:
        return (anos * 360) + (meses * 30) + dias

    def _safe_str(self, value: Any) -> str:
        return str(value or "").strip()

    def _serialize_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value

    def _date_to_iso(self, value: Any) -> str | None:
        serialized = self._serialize_value(value)
        if serialized is None:
            return None
        return str(serialized)

    def _parse_date_or_none(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        raw = str(value).strip()
        if not raw:
            return None

        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_bool_or_none(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        raw = str(value or "").strip().lower()
        if raw in {"true", "1", "sim", "s", "yes"}:
            return True
        if raw in {"false", "0", "nao", "não", "n", "no"}:
            return False
        return None

    def _pendencia(
        self,
        *,
        codigo: str,
        campo: str,
        pergunta: str,
        origem: str,
        input_kind: str = "text",
        placeholder: str | None = None,
        options: list[dict[str, str]] | None = None,
        resposta_atual: Any = None,
    ) -> dict[str, Any]:
        return {
            "codigo": codigo,
            "campo": campo,
            "pergunta": pergunta,
            "origem": origem,
            "input_kind": input_kind,
            "placeholder": placeholder,
            "options": options or [],
            "resposta_atual": resposta_atual,
        }

    # =========================
    # banco
    # =========================
    def _get_militar(self, militar_id: int) -> MilitarModel:
        militar = self.db.query(MilitarModel).filter(MilitarModel.id == militar_id).first()
        if not militar:
            raise ValueError("Militar não encontrado.")
        return militar

    def _get_periodos(self, militar_id: int) -> Iterable[MilitarPeriodoServicoModel]:
        return (
            self.db.query(MilitarPeriodoServicoModel)
            .filter(MilitarPeriodoServicoModel.militar_id == militar_id)
            .order_by(MilitarPeriodoServicoModel.data_inicio.asc())
            .all()
        )

    def _build_militar_snapshot(self, militar: MilitarModel) -> dict[str, Any]:
        return {
            "id": militar.id,
            "om": militar.om,
            "posto_graduacao": militar.posto_graduacao,
            "nome_completo": militar.nome_completo,
            "nome_guerra": militar.nome_guerra,
            "identidade": militar.identidade,
            "cpf": militar.cpf,
            "data_praca": militar.data_praca,
            "apresentacao_om": militar.apresentacao_om,
            "apresentacao_gu": militar.apresentacao_gu,
            "data_incorporacao": getattr(militar, "data_incorporacao", None),
            "data_engajamento": getattr(militar, "data_engajamento", None),
            "data_reengajamento": getattr(militar, "data_reengajamento", None),
            "data_desengajamento": getattr(militar, "data_desengajamento", None),
            "data_licenciamento": getattr(militar, "data_licenciamento", None),
            "data_exclusao_servico_ativo": getattr(militar, "data_exclusao_servico_ativo", None),
            "tempo_servico_anterior_anos": getattr(militar, "tempo_servico_anterior_anos", 0) or 0,
            "tempo_servico_anterior_meses": getattr(militar, "tempo_servico_anterior_meses", 0) or 0,
            "tempo_servico_anterior_dias": getattr(militar, "tempo_servico_anterior_dias", 0) or 0,
            "tempo_servico_publico_anos": getattr(militar, "tempo_servico_publico_anos", 0) or 0,
            "tempo_servico_publico_meses": getattr(militar, "tempo_servico_publico_meses", 0) or 0,
            "tempo_servico_publico_dias": getattr(militar, "tempo_servico_publico_dias", 0) or 0,
            "observacoes_calculo": getattr(militar, "observacoes_calculo", None),
        }

    def _build_periodo_snapshot(self, item: MilitarPeriodoServicoModel) -> dict[str, Any]:
        return {
            "id": item.id,
            "militar_id": item.militar_id,
            "tipo_registro": getattr(item, "tipo_registro", None),
            "subtipo_registro": getattr(item, "subtipo_registro", None),
            "natureza_servico": getattr(item, "natureza_servico", None),
            "categoria_tempo": getattr(item, "categoria_tempo", None),
            "origem": getattr(item, "origem", None),
            "data_inicio": getattr(item, "data_inicio", None),
            "data_fim": getattr(item, "data_fim", None),
            "computa_tempo": getattr(item, "computa_tempo", True),
            "arregimentado": getattr(item, "arregimentado", False),
            "dias_lancados_override": getattr(item, "dias_lancados_override", None),
            "documento_referencia": getattr(item, "documento_referencia", None),
            "status_calculo": getattr(item, "status_calculo", None),
            "om_origem": getattr(item, "om_origem", None),
            "om_destino": getattr(item, "om_destino", None),
            "descricao": getattr(item, "descricao", None),
            "observacoes": getattr(item, "observacoes", None),
        }

    # =========================
    # legislação
    # =========================
    def _get_legislacao_aplicada(self) -> list[dict[str, Any]]:
        items = (
            self.db.query(LegislacaoModel)
            .order_by(LegislacaoModel.updated_at.desc())
            .limit(5)
            .all()
        )

        if not items:
            return [
                {
                    "codigo": "BASE_NORMATIVA_PENDENTE",
                    "titulo": "Base normativa ainda não cadastrada no banco de legislações",
                    "tipo": "referencia_interna",
                    "orgao": None,
                    "numero": None,
                    "ano": None,
                    "url_oficial": None,
                    "ementa": "Cadastre a portaria/legislação oficial para exibição jurídica no preview.",
                    "artigos": [],
                }
            ]

        result = []
        for item in items:
            artigos = []
            palavras = getattr(item, "palavras_chave", None)
            if palavras:
                artigos = [p.strip() for p in palavras.split(",") if p.strip()][:5]

            result.append(
                {
                    "codigo": getattr(item, "codigo", None) or f"leg-{item.id}",
                    "titulo": item.titulo,
                    "tipo": getattr(item, "tipo", None),
                    "orgao": getattr(item, "orgao", None),
                    "numero": getattr(item, "numero", None),
                    "ano": getattr(item, "ano", None),
                    "url_oficial": getattr(item, "url_oficial", None),
                    "ementa": getattr(item, "ementa", None),
                    "artigos": artigos,
                }
            )
        return result

    # =========================
    # diff + projeção
    # =========================
    def _project_respostas(
        self,
        militar: dict[str, Any],
        periodos: list[dict[str, Any]],
        respostas: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        respostas = respostas or {}

        aplicadas = {}
        diff = {
            "total_alteracoes": 0,
            "alteracoes_militar": [],
            "alteracoes_periodos": [],
        }

        periodos_by_id = {int(item["id"]): item for item in periodos}

        def add_militar_change(codigo: str, campo: str, antes: Any, depois: Any):
            if self._serialize_value(antes) == self._serialize_value(depois):
                return
            diff["alteracoes_militar"].append(
                {
                    "codigo": codigo,
                    "campo": campo,
                    "antes": self._serialize_value(antes),
                    "depois": self._serialize_value(depois),
                }
            )
            diff["total_alteracoes"] += 1

        def add_periodo_change(codigo: str, periodo_id: int, campo: str, antes: Any, depois: Any):
            if self._serialize_value(antes) == self._serialize_value(depois):
                return
            diff["alteracoes_periodos"].append(
                {
                    "codigo": codigo,
                    "periodo_id": periodo_id,
                    "campo": campo,
                    "antes": self._serialize_value(antes),
                    "depois": self._serialize_value(depois),
                }
            )
            diff["total_alteracoes"] += 1

        for codigo, valor in respostas.items():
            if valor in (None, ""):
                continue

            if codigo == "MISSING_DATA_PRACA":
                parsed = self._parse_date_or_none(valor)
                if parsed:
                    add_militar_change(codigo, "data_praca", militar.get("data_praca"), parsed)
                    militar["data_praca"] = parsed
                    aplicadas[codigo] = parsed.isoformat()

            elif codigo == "MISSING_APRESENTACAO_OM":
                parsed = self._parse_date_or_none(valor)
                if parsed:
                    add_militar_change(codigo, "apresentacao_om", militar.get("apresentacao_om"), parsed)
                    militar["apresentacao_om"] = parsed
                    aplicadas[codigo] = parsed.isoformat()

            elif codigo == "MISSING_APRESENTACAO_GU":
                parsed = self._parse_date_or_none(valor)
                if parsed:
                    add_militar_change(codigo, "apresentacao_gu", militar.get("apresentacao_gu"), parsed)
                    militar["apresentacao_gu"] = parsed
                    aplicadas[codigo] = parsed.isoformat()

            elif codigo.startswith("PERIODO_"):
                parts = codigo.split("_")
                if len(parts) < 3:
                    continue

                try:
                    periodo_id = int(parts[1])
                except ValueError:
                    continue

                campo = "_".join(parts[2:]).lower()
                periodo = periodos_by_id.get(periodo_id)
                if not periodo:
                    continue

                if campo == "om_origem":
                    novo = str(valor).strip()
                    add_periodo_change(codigo, periodo_id, "om_origem", periodo.get("om_origem"), novo)
                    periodo["om_origem"] = novo
                    aplicadas[codigo] = novo

                elif campo == "om_destino":
                    novo = str(valor).strip()
                    add_periodo_change(codigo, periodo_id, "om_destino", periodo.get("om_destino"), novo)
                    periodo["om_destino"] = novo
                    aplicadas[codigo] = novo

                elif campo == "documento_referencia":
                    novo = str(valor).strip()
                    add_periodo_change(codigo, periodo_id, "documento_referencia", periodo.get("documento_referencia"), novo)
                    periodo["documento_referencia"] = novo
                    aplicadas[codigo] = novo

                elif campo == "natureza_servico":
                    novo = str(valor).strip()
                    add_periodo_change(codigo, periodo_id, "natureza_servico", periodo.get("natureza_servico"), novo)
                    periodo["natureza_servico"] = novo
                    aplicadas[codigo] = novo

                elif campo == "subtipo_registro":
                    novo = str(valor).strip()
                    add_periodo_change(codigo, periodo_id, "subtipo_registro", periodo.get("subtipo_registro"), novo)
                    periodo["subtipo_registro"] = novo
                    aplicadas[codigo] = novo

                elif campo == "data_fim":
                    parsed = self._parse_date_or_none(valor)
                    if parsed:
                        add_periodo_change(codigo, periodo_id, "data_fim", periodo.get("data_fim"), parsed)
                        periodo["data_fim"] = parsed
                        aplicadas[codigo] = parsed.isoformat()

                elif campo == "arregimentado":
                    parsed = self._parse_bool_or_none(valor)
                    if parsed is not None:
                        add_periodo_change(codigo, periodo_id, "arregimentado", periodo.get("arregimentado"), parsed)
                        periodo["arregimentado"] = parsed
                        aplicadas[codigo] = parsed

                elif campo == "computa_tempo":
                    parsed = self._parse_bool_or_none(valor)
                    if parsed is not None:
                        add_periodo_change(codigo, periodo_id, "computa_tempo", periodo.get("computa_tempo"), parsed)
                        periodo["computa_tempo"] = parsed
                        aplicadas[codigo] = parsed

                elif campo == "categoria_tempo":
                    novo = str(valor).strip()
                    add_periodo_change(codigo, periodo_id, "categoria_tempo", periodo.get("categoria_tempo"), novo)
                    periodo["categoria_tempo"] = novo
                    aplicadas[codigo] = novo

        return aplicadas, diff

    def _apply_diff_to_db(
        self,
        militar_model: MilitarModel,
        periodos_model: list[MilitarPeriodoServicoModel],
        diff: dict[str, Any],
    ) -> None:
        periodos_by_id = {int(item.id): item for item in periodos_model}

        for change in diff["alteracoes_militar"]:
            campo = change["campo"]
            depois = change["depois"]

            if campo in {"data_praca", "apresentacao_om", "apresentacao_gu"}:
                setattr(militar_model, campo, self._parse_date_or_none(depois))
            else:
                setattr(militar_model, campo, depois)

        for change in diff["alteracoes_periodos"]:
            periodo = periodos_by_id.get(int(change["periodo_id"]))
            if not periodo:
                continue

            campo = change["campo"]
            depois = change["depois"]

            if campo == "data_fim":
                setattr(periodo, campo, self._parse_date_or_none(depois))
            elif campo in {"arregimentado", "computa_tempo"}:
                setattr(periodo, campo, self._parse_bool_or_none(depois))
            else:
                setattr(periodo, campo, depois)

        self.db.flush()

    # =========================
    # preview helpers
    # =========================
    def _bucket_base_legal(self, bucket: str) -> list[str]:
        refs = {
            "tc_arregimentado": ["Base legal parametrizável — contagem de tempo computado arregimentado"],
            "tc_nao_arregimentado": ["Base legal parametrizável — contagem de tempo computado não arregimentado"],
            "tc_transito": ["Base legal parametrizável — trânsito vinculado à movimentação"],
            "tc_instalacao": ["Base legal parametrizável — instalação vinculada à movimentação"],
            "tnc": ["Base legal parametrizável — hipóteses de tempo não computado"],
            "adicional": ["Base legal parametrizável — acréscimo de tempo por situação específica"],
            "tssd": ["Base legal parametrizável — tempo de serviço em situações diversas"],
            "tscmm": ["Base legal parametrizável — tempo de serviço computável para medalha militar"],
            "tsnr": ["Base legal parametrizável — tempo de serviço nacional relevante"],
            "ttes_preview": ["Regra operacional de preview do SisGes"],
        }
        return refs.get(bucket, ["Base legal parametrizável"])

    def _periodo_days(self, item: dict[str, Any], referencia_data: date) -> int:
        inicio = item["data_inicio"]
        fim = item["data_fim"] or referencia_data

        if fim < inicio:
            return 0

        if item.get("dias_lancados_override") is not None:
            return max(0, int(item["dias_lancados_override"]))

        return (fim - inicio).days + 1

    def _build_dados_utilizados(self, militar: dict[str, Any]) -> dict[str, Any]:
        return {
            "om": militar.get("om"),
            "posto_graduacao": militar.get("posto_graduacao"),
            "nome_completo": militar.get("nome_completo"),
            "nome_guerra": militar.get("nome_guerra"),
            "identidade": militar.get("identidade"),
            "cpf": militar.get("cpf"),
            "data_praca": self._date_to_iso(militar.get("data_praca")),
            "apresentacao_om": self._date_to_iso(militar.get("apresentacao_om")),
            "apresentacao_gu": self._date_to_iso(militar.get("apresentacao_gu")),
            "data_incorporacao": self._date_to_iso(militar.get("data_incorporacao")),
            "data_engajamento": self._date_to_iso(militar.get("data_engajamento")),
            "data_reengajamento": self._date_to_iso(militar.get("data_reengajamento")),
            "data_desengajamento": self._date_to_iso(militar.get("data_desengajamento")),
            "data_licenciamento": self._date_to_iso(militar.get("data_licenciamento")),
            "data_exclusao_servico_ativo": self._date_to_iso(militar.get("data_exclusao_servico_ativo")),
            "tempo_servico_anterior": {
                "anos": militar.get("tempo_servico_anterior_anos", 0),
                "meses": militar.get("tempo_servico_anterior_meses", 0),
                "dias": militar.get("tempo_servico_anterior_dias", 0),
            },
            "tempo_servico_publico": {
                "anos": militar.get("tempo_servico_publico_anos", 0),
                "meses": militar.get("tempo_servico_publico_meses", 0),
                "dias": militar.get("tempo_servico_publico_dias", 0),
            },
            "observacoes_calculo": militar.get("observacoes_calculo"),
        }

    def _build_global_pending_questions(
        self,
        militar: dict[str, Any],
        periodos: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        perguntas = []

        if not militar.get("data_praca"):
            perguntas.append(
                self._pendencia(
                    codigo="MISSING_DATA_PRACA",
                    campo="data_praca",
                    pergunta="Qual é a data oficial de praça do militar?",
                    origem="gestao_pessoal",
                    input_kind="date",
                    placeholder="Informe a data de praça",
                    resposta_atual=self._date_to_iso(militar.get("data_praca")),
                )
            )

        if not militar.get("apresentacao_om"):
            perguntas.append(
                self._pendencia(
                    codigo="MISSING_APRESENTACAO_OM",
                    campo="apresentacao_om",
                    pergunta="Qual foi a data oficial de apresentação na OM?",
                    origem="gestao_pessoal",
                    input_kind="date",
                    placeholder="Informe a data de apresentação na OM",
                    resposta_atual=self._date_to_iso(militar.get("apresentacao_om")),
                )
            )

        if not militar.get("apresentacao_gu"):
            perguntas.append(
                self._pendencia(
                    codigo="MISSING_APRESENTACAO_GU",
                    campo="apresentacao_gu",
                    pergunta="Qual foi a data oficial de apresentação na GU?",
                    origem="gestao_pessoal",
                    input_kind="date",
                    placeholder="Informe a data de apresentação na GU",
                    resposta_atual=self._date_to_iso(militar.get("apresentacao_gu")),
                )
            )

        if not periodos and (
            militar.get("tempo_servico_anterior_anos", 0)
            + militar.get("tempo_servico_anterior_meses", 0)
            + militar.get("tempo_servico_anterior_dias", 0)
            + militar.get("tempo_servico_publico_anos", 0)
            + militar.get("tempo_servico_publico_meses", 0)
            + militar.get("tempo_servico_publico_dias", 0)
            == 0
        ):
            perguntas.append(
                self._pendencia(
                    codigo="MISSING_PERIODOS_SERVICO",
                    campo="periodos_servico",
                    pergunta="Não há períodos lançados. Deseja complementar trânsito, instalação, serviço anterior ou acréscimos no Gestão de Pessoal?",
                    origem="calculo",
                    input_kind="text",
                    placeholder="Ex.: falta lançar trânsito e instalação",
                )
            )

        return perguntas

    def _classify_periodo(self, item: dict[str, Any], referencia_data: date) -> dict[str, Any]:
        tipo = self._safe_str(item.get("tipo_registro")).lower()
        subtipo = self._safe_str(item.get("subtipo_registro")).lower()
        natureza = self._safe_str(item.get("natureza_servico")).lower()
        categoria = self._safe_str(item.get("categoria_tempo")).lower()
        documento = self._safe_str(item.get("documento_referencia"))

        dias = self._periodo_days(item, referencia_data)
        pendencias = []
        conflitos = []
        confianca = 0.95
        classificacao_final = "deterministica"

        if dias == 0 and item.get("data_fim") and item["data_fim"] < item["data_inicio"]:
            conflitos.append("Data final anterior à data inicial.")
            confianca = 0.2

        if not documento:
            pendencias.append(
                self._pendencia(
                    codigo=f"PERIODO_{item['id']}_DOCUMENTO_REFERENCIA",
                    campo=f"periodo:{item['id']}:documento_referencia",
                    pergunta="Qual é o documento de referência deste período?",
                    origem="periodo_servico",
                    input_kind="text",
                    placeholder="Ex.: BI nº 095, de 1 AGO 18",
                    resposta_atual=item.get("documento_referencia"),
                )
            )
            confianca -= 0.10

        if tipo == "movimentacao":
            if not self._safe_str(item.get("om_origem")):
                pendencias.append(
                    self._pendencia(
                        codigo=f"PERIODO_{item['id']}_OM_ORIGEM",
                        campo=f"periodo:{item['id']}:om_origem",
                        pergunta="Qual foi a OM de origem desta movimentação?",
                        origem="periodo_servico",
                        input_kind="text",
                        placeholder="Informe a OM de origem",
                        resposta_atual=item.get("om_origem"),
                    )
                )
                confianca -= 0.10

            if not self._safe_str(item.get("om_destino")):
                pendencias.append(
                    self._pendencia(
                        codigo=f"PERIODO_{item['id']}_OM_DESTINO",
                        campo=f"periodo:{item['id']}:om_destino",
                        pergunta="Qual foi a OM de destino desta movimentação?",
                        origem="periodo_servico",
                        input_kind="text",
                        placeholder="Informe a OM de destino",
                        resposta_atual=item.get("om_destino"),
                    )
                )
                confianca -= 0.10

            if not item.get("data_fim"):
                pendencias.append(
                    self._pendencia(
                        codigo=f"PERIODO_{item['id']}_DATA_FIM",
                        campo=f"periodo:{item['id']}:data_fim",
                        pergunta="Qual foi a data final, apresentação ou conclusão desta movimentação?",
                        origem="periodo_servico",
                        input_kind="date",
                        placeholder="Informe a data final",
                        resposta_atual=self._date_to_iso(item.get("data_fim")),
                    )
                )
                confianca -= 0.10

            if not subtipo:
                pendencias.append(
                    self._pendencia(
                        codigo=f"PERIODO_{item['id']}_SUBTIPO_REGISTRO",
                        campo=f"periodo:{item['id']}:subtipo_registro",
                        pergunta="Esse período de movimentação foi trânsito, instalação, transferência ou outro subtipo?",
                        origem="periodo_servico",
                        input_kind="select",
                        options=[
                            {"label": "Trânsito", "value": "transito"},
                            {"label": "Instalação", "value": "instalacao"},
                            {"label": "Transferência", "value": "transferencia"},
                            {"label": "Outro", "value": "outro"},
                        ],
                        resposta_atual=item.get("subtipo_registro"),
                    )
                )
                confianca -= 0.12

        if tipo == "servico_anterior" and not natureza:
            pendencias.append(
                self._pendencia(
                    codigo=f"PERIODO_{item['id']}_NATUREZA_SERVICO",
                    campo=f"periodo:{item['id']}:natureza_servico",
                    pergunta="A natureza do serviço anterior é militar, público, privado, OFR ou acadêmico?",
                    origem="periodo_servico",
                    input_kind="select",
                    options=[
                        {"label": "Serviço militar", "value": "servico_militar"},
                        {"label": "Serviço público", "value": "servico_publico"},
                        {"label": "Serviço privado", "value": "servico_privado"},
                        {"label": "OFR", "value": "ofr"},
                        {"label": "Acadêmico", "value": "academico"},
                    ],
                    resposta_atual=item.get("natureza_servico"),
                )
            )
            confianca -= 0.15

        if tipo == "acrescimo_tempo" and not subtipo:
            pendencias.append(
                self._pendencia(
                    codigo=f"PERIODO_{item['id']}_SUBTIPO_REGISTRO",
                    campo=f"periodo:{item['id']}:subtipo_registro",
                    pergunta="Qual é o subtipo do acréscimo de tempo?",
                    origem="periodo_servico",
                    input_kind="select",
                    options=[
                        {"label": "Situações diversas", "value": "situacoes_diversas"},
                        {"label": "Guarnição especial", "value": "guarnicao_especial"},
                        {"label": "Outro", "value": "outro"},
                    ],
                    resposta_atual=item.get("subtipo_registro"),
                )
            )
            confianca -= 0.10

        bucket = "pendente_classificacao"
        motivo = "O motor não encontrou regra suficiente para classificar o período com segurança."

        if categoria == "tscmm":
            bucket = "tscmm"
            motivo = "Período lançado explicitamente como TSCMM."
        elif categoria == "tsnr":
            bucket = "tsnr"
            motivo = "Período lançado explicitamente como TSNR."
        elif categoria == "adicional":
            bucket = "adicional"
            motivo = "Período lançado como acréscimo de tempo."
        elif categoria in {"nao_computado", "não_computado"} or not item.get("computa_tempo", True):
            bucket = "tnc"
            motivo = "Período marcado como não computado ou com computa_tempo = false."
        elif tipo == "movimentacao" and subtipo in {"transito", "trânsito"}:
            bucket = "tc_transito"
            motivo = "Movimentação classificada como trânsito."
        elif tipo == "movimentacao" and subtipo in {"instalacao", "instalação"}:
            bucket = "tc_instalacao"
            motivo = "Movimentação classificada como instalação."
        elif tipo in {"servico_anterior", "serviço_anterior", "averbacao", "averbação"}:
            bucket = "tssd"
            motivo = "Tempo anterior/averbado tratado como tempo em situação diversa para análise."
        elif categoria == "computado":
            if item.get("arregimentado"):
                bucket = "tc_arregimentado"
                motivo = "Período computado e marcado como arregimentado."
            else:
                bucket = "tc_nao_arregimentado"
                motivo = "Período computado e marcado como não arregimentado."
        else:
            confianca = min(confianca, 0.55)

        if pendencias and confianca < 0.85 and bucket != "pendente_classificacao":
            classificacao_final = "probabilistica_validada"

        if bucket == "pendente_classificacao":
            classificacao_final = "pendente"

        if conflitos:
            classificacao_final = "conflito"

        return {
            "id": item["id"],
            "tipo_registro": item.get("tipo_registro"),
            "subtipo_registro": item.get("subtipo_registro"),
            "natureza_servico": item.get("natureza_servico"),
            "categoria_tempo": item.get("categoria_tempo"),
            "dias": dias,
            "bucket": bucket,
            "data_inicio": self._date_to_iso(item.get("data_inicio")),
            "data_fim": self._date_to_iso(item.get("data_fim")),
            "documento_referencia": item.get("documento_referencia"),
            "om_origem": item.get("om_origem"),
            "om_destino": item.get("om_destino"),
            "classificacao_final": classificacao_final,
            "confianca": max(0.0, round(confianca, 2)),
            "motivo_textual": motivo,
            "base_legal": self._bucket_base_legal(bucket),
            "perguntas_pendentes": pendencias,
            "conflitos": conflitos,
        }

    def _build_conflitos_temporais(self, itens_processados: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conflitos = []
        itens_validos = [
            item for item in itens_processados if item["bucket"] != "pendente_classificacao"
        ]

        for i in range(len(itens_validos)):
            atual = itens_validos[i]
            inicio_atual = atual["data_inicio"]
            fim_atual = atual["data_fim"] or atual["data_inicio"]

            for j in range(i + 1, len(itens_validos)):
                prox = itens_validos[j]
                inicio_prox = prox["data_inicio"]
                fim_prox = prox["data_fim"] or prox["data_inicio"]

                if inicio_prox <= fim_atual and inicio_atual <= fim_prox:
                    conflitos.append(
                        {
                            "tipo": "sobreposicao_potencial",
                            "periodo_a": atual["id"],
                            "periodo_b": prox["id"],
                            "mensagem": "Há sobreposição potencial entre períodos lançados; revisar para evitar dupla contagem.",
                        }
                    )

        uniq = []
        seen = set()
        for item in conflitos:
            key = (item["periodo_a"], item["periodo_b"], item["tipo"])
            if key not in seen:
                seen.add(key)
                uniq.append(item)
        return uniq

    def _preview_from_snapshots(
        self,
        *,
        militar_id: int,
        referencia_data: date,
        militar: dict[str, Any],
        periodos: list[dict[str, Any]],
        respostas_aplicadas: dict[str, Any] | None = None,
        diff: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tempo_anterior_dias = self._ymd_to_days(
            militar.get("tempo_servico_anterior_anos", 0),
            militar.get("tempo_servico_anterior_meses", 0),
            militar.get("tempo_servico_anterior_dias", 0),
        )

        tempo_servico_publico_dias = self._ymd_to_days(
            militar.get("tempo_servico_publico_anos", 0),
            militar.get("tempo_servico_publico_meses", 0),
            militar.get("tempo_servico_publico_dias", 0),
        )

        buckets = {
            "tc_arregimentado": 0,
            "tc_nao_arregimentado": 0,
            "tc_transito": 0,
            "tc_instalacao": 0,
            "tnc": 0,
            "adicional": 0,
            "tssd": 0,
            "tscmm": 0,
            "tsnr": 0,
        }

        itens_processados = []
        pendencias = self._build_global_pending_questions(militar, periodos)

        for item in periodos:
            detalhe = self._classify_periodo(item, referencia_data)
            itens_processados.append(detalhe)

            bucket = detalhe["bucket"]
            if bucket in buckets:
                buckets[bucket] += detalhe["dias"]

            pendencias.extend(detalhe["perguntas_pendentes"])

        conflitos = self._build_conflitos_temporais(itens_processados)
        for item in itens_processados:
            for conflito in item["conflitos"]:
                conflitos.append(
                    {
                        "tipo": "registro_invalido",
                        "periodo_a": item["id"],
                        "periodo_b": None,
                        "mensagem": conflito,
                    }
                )

        uniq_pendencias = []
        seen_p = set()
        for pergunta in pendencias:
            key = (pergunta["codigo"], pergunta["campo"], pergunta["pergunta"])
            if key not in seen_p:
                seen_p.add(key)
                uniq_pendencias.append(pergunta)

        status_preview = "ok"
        if conflitos:
            status_preview = "conflito"
        elif uniq_pendencias:
            status_preview = "pendente_dados"

        ttes_preview_dias = (
            tempo_anterior_dias
            + tempo_servico_publico_dias
            + buckets["tc_arregimentado"]
            + buckets["tc_nao_arregimentado"]
            + buckets["tc_transito"]
            + buckets["tc_instalacao"]
            + buckets["adicional"]
        )

        justificativa_geral = [
            {
                "bucket": "tc_arregimentado",
                "motivo": "Soma dos períodos computados marcados como arregimentados.",
                "base_legal": self._bucket_base_legal("tc_arregimentado"),
                "dias": buckets["tc_arregimentado"],
            },
            {
                "bucket": "tc_nao_arregimentado",
                "motivo": "Soma dos períodos computados não arregimentados.",
                "base_legal": self._bucket_base_legal("tc_nao_arregimentado"),
                "dias": buckets["tc_nao_arregimentado"],
            },
            {
                "bucket": "tc_transito",
                "motivo": "Soma dos períodos de movimentação classificados como trânsito.",
                "base_legal": self._bucket_base_legal("tc_transito"),
                "dias": buckets["tc_transito"],
            },
            {
                "bucket": "tc_instalacao",
                "motivo": "Soma dos períodos de movimentação classificados como instalação.",
                "base_legal": self._bucket_base_legal("tc_instalacao"),
                "dias": buckets["tc_instalacao"],
            },
            {
                "bucket": "tnc",
                "motivo": "Soma dos períodos marcados como não computados.",
                "base_legal": self._bucket_base_legal("tnc"),
                "dias": buckets["tnc"],
            },
            {
                "bucket": "adicional",
                "motivo": "Soma dos períodos lançados como adicional.",
                "base_legal": self._bucket_base_legal("adicional"),
                "dias": buckets["adicional"],
            },
            {
                "bucket": "tssd",
                "motivo": "Soma informativa de tempos classificados como situação diversa.",
                "base_legal": self._bucket_base_legal("tssd"),
                "dias": buckets["tssd"],
            },
            {
                "bucket": "ttes_preview",
                "motivo": "Preview operacional do SisGes. Fórmula atual: tempo anterior + tempo público + TC + trânsito + instalação + adicional.",
                "base_legal": self._bucket_base_legal("ttes_preview"),
                "dias": ttes_preview_dias,
            },
        ]

        return {
            "militar_id": militar_id,
            "referencia_data": referencia_data.isoformat(),
            "motor_versao": "calc_norma_v4_diff_approval",
            "status_preview": status_preview,
            "respostas_aplicadas": respostas_aplicadas or {},
            "diff_sugerido": diff
            or {
                "total_alteracoes": 0,
                "alteracoes_militar": [],
                "alteracoes_periodos": [],
            },
            "dados_utilizados_do_gestao": self._build_dados_utilizados(militar),
            "legislacao_aplicada": self._get_legislacao_aplicada(),
            "justificativa_geral": justificativa_geral,
            "pendencias": uniq_pendencias,
            "conflitos": conflitos,
            "tempo_anterior": self._normalize_days(tempo_anterior_dias).__dict__,
            "tempo_servico_publico": self._normalize_days(tempo_servico_publico_dias).__dict__,
            "tc_arregimentado": self._normalize_days(buckets["tc_arregimentado"]).__dict__,
            "tc_nao_arregimentado": self._normalize_days(buckets["tc_nao_arregimentado"]).__dict__,
            "tc_transito": self._normalize_days(buckets["tc_transito"]).__dict__,
            "tc_instalacao": self._normalize_days(buckets["tc_instalacao"]).__dict__,
            "tnc": self._normalize_days(buckets["tnc"]).__dict__,
            "adicional": self._normalize_days(buckets["adicional"]).__dict__,
            "tssd": self._normalize_days(buckets["tssd"]).__dict__,
            "tscmm": self._normalize_days(buckets["tscmm"]).__dict__,
            "tsnr": self._normalize_days(buckets["tsnr"]).__dict__,
            "ttes_preview": self._normalize_days(ttes_preview_dias).__dict__,
            "total_preview": self._normalize_days(ttes_preview_dias).__dict__,
            "itens_processados": itens_processados,
            "regra_preview": {
                "versao": "calc_norma_v4_diff_approval",
                "convencao_saida": "30_360",
                "dias_periodo": "dias_corridos_reais",
                "modo_decisao": "probabilistico_interno_deterministico_externo",
                "observacao": "Antes de gravar, o SisGes calcula um diff explícito das alterações sugeridas.",
            },
        }

    # =========================
    # persistência
    # =========================
    def _save_snapshot_record(
        self,
        *,
        preview: dict[str, Any],
        militar_id: int,
        referencia_data: date,
        observacoes: str | None,
        calculado_por_user_id: str | None,
    ) -> CalculoTempoServicoModel:
        tc_ar = preview["tc_arregimentado"]
        tc_na = preview["tc_nao_arregimentado"]
        tc_tr = preview["tc_transito"]
        tc_in = preview["tc_instalacao"]
        total = preview["total_preview"]

        tempo_computado_dias = (
            tc_ar["total_dias"]
            + tc_na["total_dias"]
            + tc_tr["total_dias"]
            + tc_in["total_dias"]
        )
        tempo_computado = self._normalize_days(tempo_computado_dias)

        registro = CalculoTempoServicoModel(
            militar_id=militar_id,
            referencia_data=referencia_data,
            tempo_arregimentado_anos=tc_ar["anos"],
            tempo_arregimentado_meses=tc_ar["meses"],
            tempo_arregimentado_dias=tc_ar["dias"],
            tempo_nao_arregimentado_anos=tc_na["anos"],
            tempo_nao_arregimentado_meses=tc_na["meses"],
            tempo_nao_arregimentado_dias=tc_na["dias"],
            tempo_computado_anos=tempo_computado.anos,
            tempo_computado_meses=tempo_computado.meses,
            tempo_computado_dias=tempo_computado.dias,
            tempo_total_anos=total["anos"],
            tempo_total_meses=total["meses"],
            tempo_total_dias=total["dias"],
            base_legal_json={
                "preview": preview,
                "motor_versao": preview.get("motor_versao"),
                "status_preview": preview.get("status_preview"),
                "justificativa_geral": preview.get("justificativa_geral"),
                "legislacao_aplicada": preview.get("legislacao_aplicada"),
                "pendencias": preview.get("pendencias"),
                "conflitos": preview.get("conflitos"),
                "respostas_aplicadas": preview.get("respostas_aplicadas"),
                "diff_sugerido": preview.get("diff_sugerido"),
            },
            observacoes=observacoes,
            calculado_por_user_id=calculado_por_user_id,
        )

        self.db.add(registro)
        self.db.flush()
        return registro

    def list_history(self, militar_id: int, limit: int = 20) -> list[dict[str, Any]]:
        items = (
            self.db.query(CalculoTempoServicoModel)
            .filter(CalculoTempoServicoModel.militar_id == militar_id)
            .order_by(CalculoTempoServicoModel.created_at.desc())
            .limit(limit)
            .all()
        )

        result = []
        for item in items:
            result.append(
                {
                    "id": item.id,
                    "militar_id": item.militar_id,
                    "referencia_data": item.referencia_data.isoformat(),
                    "tempo_arregimentado": {
                        "anos": item.tempo_arregimentado_anos,
                        "meses": item.tempo_arregimentado_meses,
                        "dias": item.tempo_arregimentado_dias,
                    },
                    "tempo_nao_arregimentado": {
                        "anos": item.tempo_nao_arregimentado_anos,
                        "meses": item.tempo_nao_arregimentado_meses,
                        "dias": item.tempo_nao_arregimentado_dias,
                    },
                    "tempo_computado": {
                        "anos": item.tempo_computado_anos,
                        "meses": item.tempo_computado_meses,
                        "dias": item.tempo_computado_dias,
                    },
                    "tempo_total": {
                        "anos": item.tempo_total_anos,
                        "meses": item.tempo_total_meses,
                        "dias": item.tempo_total_dias,
                    },
                    "observacoes": item.observacoes,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                    "base_legal_json": item.base_legal_json,
                }
            )
        return result

    # =========================
    # API pública
    # =========================
    def preview(self, militar_id: int, referencia_data: date) -> dict[str, Any]:
        militar_model = self._get_militar(militar_id)
        periodos_model = list(self._get_periodos(militar_id))

        militar = self._build_militar_snapshot(militar_model)
        periodos = [self._build_periodo_snapshot(item) for item in periodos_model]

        return self._preview_from_snapshots(
            militar_id=militar_id,
            referencia_data=referencia_data,
            militar=militar,
            periodos=periodos,
            respostas_aplicadas={},
        )

    def preview_complementado(
        self,
        militar_id: int,
        referencia_data: date,
        respostas: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        militar_model = self._get_militar(militar_id)
        periodos_model = list(self._get_periodos(militar_id))

        militar = self._build_militar_snapshot(militar_model)
        periodos = [self._build_periodo_snapshot(item) for item in periodos_model]

        respostas_aplicadas, diff = self._project_respostas(militar, periodos, respostas)

        return self._preview_from_snapshots(
            militar_id=militar_id,
            referencia_data=referencia_data,
            militar=militar,
            periodos=periodos,
            respostas_aplicadas=respostas_aplicadas,
            diff=diff,
        )

    def diff_respostas(
        self,
        militar_id: int,
        referencia_data: date,
        respostas: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        militar_model = self._get_militar(militar_id)
        periodos_model = list(self._get_periodos(militar_id))

        militar = self._build_militar_snapshot(militar_model)
        periodos = [self._build_periodo_snapshot(item) for item in periodos_model]

        respostas_aplicadas, diff = self._project_respostas(militar, periodos, respostas)

        preview = self._preview_from_snapshots(
            militar_id=militar_id,
            referencia_data=referencia_data,
            militar=militar,
            periodos=periodos,
            respostas_aplicadas=respostas_aplicadas,
            diff=diff,
        )

        return {
            "militar_id": militar_id,
            "referencia_data": referencia_data.isoformat(),
            "respostas_aplicadas": respostas_aplicadas,
            "diff": diff,
            "preview": preview,
        }

    def approve_and_save(
        self,
        *,
        militar_id: int,
        referencia_data: date,
        respostas: dict[str, Any] | None = None,
        observacoes: str | None = None,
        calculado_por_user_id: str | None = None,
    ) -> dict[str, Any]:
        militar_model = self._get_militar(militar_id)
        periodos_model = list(self._get_periodos(militar_id))

        militar = self._build_militar_snapshot(militar_model)
        periodos = [self._build_periodo_snapshot(item) for item in periodos_model]

        respostas_aplicadas, diff = self._project_respostas(militar, periodos, respostas)

        preview = self._preview_from_snapshots(
            militar_id=militar_id,
            referencia_data=referencia_data,
            militar=militar,
            periodos=periodos,
            respostas_aplicadas=respostas_aplicadas,
            diff=diff,
        )

        with atomic(self.db):
            self._apply_diff_to_db(militar_model, periodos_model, diff)

            registro = self._save_snapshot_record(
                preview=preview,
                militar_id=militar_id,
                referencia_data=referencia_data,
                observacoes=observacoes,
                calculado_por_user_id=calculado_por_user_id,
            )

        return {
            "snapshot_id": registro.id,
            "diff_aprovado": diff,
            "respostas_aplicadas": respostas_aplicadas,
            "preview": preview,
        }
