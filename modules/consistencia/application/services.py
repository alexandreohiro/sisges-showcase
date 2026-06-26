from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from infra.persistence.models import (
    CalculoTempoServicoModel,
    CTSMModel,
    DocumentModel,
    FolhaAlteracaoModel,
    MilitarModel,
    MilitarPeriodoServicoModel,
    TarefaModel,
)


SEVERITY_SCORE = {
    "critica": 100,
    "alta": 80,
    "media": 50,
    "baixa": 20,
}


@dataclass(frozen=True)
class ConsistencyIssue:
    regra: str
    modulo: str
    tipo: str
    severidade: str
    militar_id: int | None
    referencia_tipo: str
    referencia_id: str
    titulo: str
    descricao: str
    acao_recomendada: str
    motivo_regra: str
    payload: dict[str, Any]

    @property
    def score(self) -> int:
        return SEVERITY_SCORE[self.severidade]

    @property
    def fingerprint(self) -> str:
        return "|".join(
            [
                self.regra,
                self.referencia_tipo,
                self.referencia_id,
                str(self.militar_id or ""),
            ]
        )[:160]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "regra": self.regra,
            "modulo": self.modulo,
            "tipo": self.tipo,
            "severidade": self.severidade,
            "score": self.score,
            "militar_id": self.militar_id,
            "referencia_tipo": self.referencia_tipo,
            "referencia_id": self.referencia_id,
            "titulo": self.titulo,
            "descricao": self.descricao,
            "acao_recomendada": self.acao_recomendada,
            "motivo_regra": self.motivo_regra,
            "payload": self.payload,
        }


class ConsistenciaService:
    def __init__(self, db):
        self.db = db

    def reprocessar(self, militar_id: int | None = None) -> list[ConsistencyIssue]:
        issues: list[ConsistencyIssue] = []
        issues.extend(self._calculos_sem_data_praca(militar_id))
        issues.extend(self._ctsm_sem_calculo(militar_id))
        issues.extend(self._ctsm_snapshot_desatualizado(militar_id))
        issues.extend(self._folhas_sem_vinculo_correto(militar_id))
        issues.extend(self._documentos_sem_rastreabilidade())
        issues.extend(self._periodos_invalidos(militar_id))
        issues.extend(self._tarefas_concluidas_sem_artefato(militar_id))
        return sorted(issues, key=lambda item: item.score, reverse=True)

    def summary(self, militar_id: int | None = None) -> dict[str, Any]:
        issues = self.reprocessar(militar_id=militar_id)
        by_module: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for issue in issues:
            by_module[issue.modulo] = by_module.get(issue.modulo, 0) + 1
            by_severity[issue.severidade] = by_severity.get(issue.severidade, 0) + 1
        return {
            "total": len(issues),
            "por_modulo": by_module,
            "por_severidade": by_severity,
            "maior_severidade": issues[0].severidade if issues else None,
        }

    def _calculos_sem_data_praca(self, militar_id: int | None) -> list[ConsistencyIssue]:
        query = (
            self.db.query(CalculoTempoServicoModel, MilitarModel)
            .join(MilitarModel, MilitarModel.id == CalculoTempoServicoModel.militar_id)
            .filter(MilitarModel.data_praca.is_(None))
        )
        if militar_id is not None:
            query = query.filter(CalculoTempoServicoModel.militar_id == militar_id)

        return [
            ConsistencyIssue(
                regra="CALCULO_SEM_DATA_PRACA",
                modulo="calculo",
                tipo="pendencia_dado",
                severidade="alta",
                militar_id=calculo.militar_id,
                referencia_tipo="calculo_tempo_servico",
                referencia_id=str(calculo.id),
                titulo="Calculo salvo sem data de praca",
                descricao="O snapshot de calculo foi salvo para militar sem data_praca cadastrada.",
                acao_recomendada="COMPLETAR_DADO_DATA_PRACA",
                motivo_regra="Militar.data_praca esta vazio para calculo persistido.",
                payload={
                    "calculo_id": calculo.id,
                    "militar_nome": militar.nome_completo,
                    "referencia_data": calculo.referencia_data.isoformat(),
                },
            )
            for calculo, militar in query.all()
        ]

    def _ctsm_sem_calculo(self, militar_id: int | None) -> list[ConsistencyIssue]:
        query = self.db.query(CTSMModel)
        if militar_id is not None:
            query = query.filter(CTSMModel.militar_id == militar_id)

        issues = []
        for ctsm in query.all():
            calculo_inexistente = ctsm.calculo_id and not self._calculo_exists(ctsm.calculo_id)
            if ctsm.calculo_id and not calculo_inexistente:
                continue
            issues.append(
                ConsistencyIssue(
                    regra="CTSM_SEM_CALCULO_APROVADO",
                    modulo="ctsm",
                    tipo="bloqueio",
                    severidade="critica",
                    militar_id=ctsm.militar_id,
                    referencia_tipo="ctsm",
                    referencia_id=str(ctsm.id),
                    titulo="CTSM sem calculo aprovado",
                    descricao="A CTSM nao possui snapshot de calculo aprovado valido.",
                    acao_recomendada="GERAR_CTSM_A_PARTIR_DE_CALCULO",
                    motivo_regra="CTSM.calculo_id vazio ou apontando para calculo inexistente.",
                    payload={"ctsm_id": ctsm.id, "calculo_id": ctsm.calculo_id},
                )
            )
        return issues

    def _ctsm_snapshot_desatualizado(self, militar_id: int | None) -> list[ConsistencyIssue]:
        query = self.db.query(CTSMModel).filter(CTSMModel.status == "emitida")
        if militar_id is not None:
            query = query.filter(CTSMModel.militar_id == militar_id)

        issues = []
        for ctsm in query.all():
            if not ctsm.calculo_id:
                continue
            latest = self._latest_calculo(ctsm.militar_id)
            if not latest or latest.id == ctsm.calculo_id:
                continue
            if ctsm.emitido_em and latest.created_at <= ctsm.emitido_em:
                continue
            issues.append(
                ConsistencyIssue(
                    regra="CTSM_SNAPSHOT_DESATUALIZADO",
                    modulo="ctsm",
                    tipo="alerta",
                    severidade="alta",
                    militar_id=ctsm.militar_id,
                    referencia_tipo="ctsm",
                    referencia_id=str(ctsm.id),
                    titulo="CTSM emitida com snapshot desatualizado",
                    descricao="Existe calculo mais recente que o snapshot usado na CTSM emitida.",
                    acao_recomendada="REEMITIR_CTSM",
                    motivo_regra="Ultimo calculo do militar e posterior ao calculo vinculado a CTSM.",
                    payload={
                        "ctsm_id": ctsm.id,
                        "calculo_vinculado_id": ctsm.calculo_id,
                        "calculo_mais_recente_id": latest.id,
                    },
                )
            )
        return issues

    def _folhas_sem_vinculo_correto(self, militar_id: int | None) -> list[ConsistencyIssue]:
        query = self.db.query(FolhaAlteracaoModel)
        if militar_id is not None:
            query = query.filter(FolhaAlteracaoModel.militar_id == militar_id)

        issues = []
        for folha in query.all():
            if not self._militar_exists(folha.militar_id):
                issues.append(
                    self._folha_issue(
                        folha,
                        "FOLHA_MILITAR_INEXISTENTE",
                        "Folha vinculada a militar inexistente",
                        "FolhaAlteracaoModel.militar_id nao existe em militar.",
                    )
                )
            elif folha.periodo_fim < folha.periodo_inicio:
                issues.append(
                    self._folha_issue(
                        folha,
                        "FOLHA_PERIODO_INVALIDO",
                        "Folha com periodo final menor que inicial",
                        "FolhaAlteracaoModel.periodo_fim e menor que periodo_inicio.",
                    )
                )
        return issues

    def _documentos_sem_rastreabilidade(self) -> list[ConsistencyIssue]:
        issues = []
        for doc in self.db.query(DocumentModel).all():
            missing_hash = not doc.output_sha256
            missing_template = doc.source_module == "compilador" and not doc.template_version
            if not missing_hash and not missing_template:
                continue
            issues.append(
                ConsistencyIssue(
                    regra="DOCUMENTO_SEM_RASTREABILIDADE",
                    modulo="documents",
                    tipo="alerta",
                    severidade="media",
                    militar_id=self._militar_id_from_document(doc),
                    referencia_tipo="documents",
                    referencia_id=doc.id,
                    titulo="Documento sem hash ou versao de template",
                    descricao="Documento gerado sem metadados suficientes para auditoria.",
                    acao_recomendada="REPROCESSAR_DOCUMENTO",
                    motivo_regra="Document.output_sha256 ausente ou template_version ausente.",
                    payload={
                        "document_id": doc.id,
                        "source_module": doc.source_module,
                        "missing_output_hash": missing_hash,
                        "missing_template_version": missing_template,
                    },
                )
            )
        return issues

    def _periodos_invalidos(self, militar_id: int | None) -> list[ConsistencyIssue]:
        query = self.db.query(MilitarPeriodoServicoModel)
        if militar_id is not None:
            query = query.filter(MilitarPeriodoServicoModel.militar_id == militar_id)

        periodos = query.order_by(
            MilitarPeriodoServicoModel.militar_id.asc(),
            MilitarPeriodoServicoModel.data_inicio.asc(),
        ).all()
        issues = []
        by_militar: dict[int, list[MilitarPeriodoServicoModel]] = {}
        for periodo in periodos:
            by_militar.setdefault(periodo.militar_id, []).append(periodo)
            if periodo.data_fim and periodo.data_fim < periodo.data_inicio:
                issues.append(self._periodo_issue(periodo, "PERIODO_DATA_INVALIDA"))
            if periodo.tipo_registro == "movimentacao" and (
                not periodo.om_origem or not periodo.om_destino
            ):
                issues.append(self._periodo_issue(periodo, "MOVIMENTACAO_SEM_ORIGEM_DESTINO"))

        for militar_periodos in by_militar.values():
            validos = [
                item for item in militar_periodos if not item.data_fim or item.data_fim >= item.data_inicio
            ]
            for index, atual in enumerate(validos):
                fim_atual = atual.data_fim or date.max
                for proximo in validos[index + 1 :]:
                    if proximo.data_inicio <= fim_atual:
                        issues.append(self._sobreposicao_issue(atual, proximo))
        return issues

    def _tarefas_concluidas_sem_artefato(self, militar_id: int | None) -> list[ConsistencyIssue]:
        status_concluido = {"concluida", "concluída", "fechada", "finalizada"}
        query = self.db.query(TarefaModel)
        if militar_id is not None:
            query = query.filter(TarefaModel.militar_id == militar_id)

        issues = []
        for tarefa in query.all():
            if (tarefa.status or "").lower() not in status_concluido:
                continue
            origem = (tarefa.origem_modulo or "").lower()
            tipo = (tarefa.tipo or "").lower()
            exige_artefato = origem in {"compilador", "ctsm", "folhas"} or any(
                token in tipo for token in ("gerar", "emitir", "compilar")
            )
            if not exige_artefato or tarefa.resultado_resumido:
                continue
            issues.append(
                ConsistencyIssue(
                    regra="TAREFA_CONCLUIDA_SEM_ARTEFATO",
                    modulo="tarefas",
                    tipo="alerta",
                    severidade="media",
                    militar_id=tarefa.militar_id,
                    referencia_tipo="tarefa",
                    referencia_id=str(tarefa.id),
                    titulo="Tarefa concluida sem artefato esperado",
                    descricao="Tarefa operacional foi concluida sem registro de resultado ou artefato.",
                    acao_recomendada="ANEXAR_OU_REGISTRAR_ARTEFATO",
                    motivo_regra="Status concluido com origem/tipo documental e resultado_resumido vazio.",
                    payload={"tarefa_id": tarefa.id, "origem_modulo": tarefa.origem_modulo},
                )
            )
        return issues

    def _folha_issue(
        self,
        folha: FolhaAlteracaoModel,
        regra: str,
        titulo: str,
        motivo: str,
    ) -> ConsistencyIssue:
        return ConsistencyIssue(
            regra=regra,
            modulo="folhas",
            tipo="bloqueio",
            severidade="alta",
            militar_id=folha.militar_id,
            referencia_tipo="folha_alteracao",
            referencia_id=str(folha.id),
            titulo=titulo,
            descricao="Folha de alteracao precisa de revisao de vinculo antes de seguir fluxo.",
            acao_recomendada="REVISAR_FOLHA",
            motivo_regra=motivo,
            payload={"folha_id": folha.id, "status": folha.status},
        )

    def _periodo_issue(
        self,
        periodo: MilitarPeriodoServicoModel,
        regra: str,
    ) -> ConsistencyIssue:
        is_movimentacao = regra == "MOVIMENTACAO_SEM_ORIGEM_DESTINO"
        return ConsistencyIssue(
            regra=regra,
            modulo="gestao_pessoal",
            tipo="pendencia_dado",
            severidade="alta" if is_movimentacao else "critica",
            militar_id=periodo.militar_id,
            referencia_tipo="militar_periodo_servico",
            referencia_id=str(periodo.id),
            titulo=(
                "Movimentacao sem origem/destino"
                if is_movimentacao
                else "Periodo com data final menor que inicial"
            ),
            descricao="Periodo de servico possui dados inconsistentes para calculo e documentos.",
            acao_recomendada="CORRIGIR_PERIODO_SERVICO",
            motivo_regra=(
                "Movimentacao exige om_origem e om_destino."
                if is_movimentacao
                else "MilitarPeriodoServicoModel.data_fim menor que data_inicio."
            ),
            payload={
                "periodo_id": periodo.id,
                "data_inicio": periodo.data_inicio.isoformat(),
                "data_fim": periodo.data_fim.isoformat() if periodo.data_fim else None,
            },
        )

    def _sobreposicao_issue(
        self,
        atual: MilitarPeriodoServicoModel,
        proximo: MilitarPeriodoServicoModel,
    ) -> ConsistencyIssue:
        return ConsistencyIssue(
            regra="PERIODO_SOBREPOSICAO",
            modulo="gestao_pessoal",
            tipo="alerta",
            severidade="alta",
            militar_id=atual.militar_id,
            referencia_tipo="militar_periodo_servico",
            referencia_id=str(atual.id),
            titulo="Periodo de servico com sobreposicao",
            descricao="Dois periodos do mesmo militar se sobrepoem e podem gerar dupla contagem.",
            acao_recomendada="REVISAR_SOBREPOSICAO_PERIODOS",
            motivo_regra="Intervalos de datas se cruzam para o mesmo militar.",
            payload={"periodo_a": atual.id, "periodo_b": proximo.id},
        )

    def _militar_exists(self, militar_id: int) -> bool:
        return self.db.query(MilitarModel.id).filter(MilitarModel.id == militar_id).first() is not None

    def _calculo_exists(self, calculo_id: int) -> bool:
        return (
            self.db.query(CalculoTempoServicoModel.id)
            .filter(CalculoTempoServicoModel.id == calculo_id)
            .first()
            is not None
        )

    def _latest_calculo(self, militar_id: int) -> CalculoTempoServicoModel | None:
        return (
            self.db.query(CalculoTempoServicoModel)
            .filter(CalculoTempoServicoModel.militar_id == militar_id)
            .order_by(CalculoTempoServicoModel.created_at.desc())
            .first()
        )

    @staticmethod
    def _militar_id_from_document(doc: DocumentModel) -> int | None:
        metadata = doc.metadata_json or {}
        value = metadata.get("militar_id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
