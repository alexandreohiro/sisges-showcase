from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from infra.config import settings
from infra.persistence.models import (
    CalculoTempoServicoModel,
    CompilerFileModel,
    CompilerRunModel,
    CompilerVariableSnapshotModel,
    CTSMModel,
    FolhaAlteracaoModel,
    FolhaEventoModel,
    MilitarModel,
    MilitarPeriodoServicoModel,
    SicapexEventoFuncionalModel,
    SicapexImportFileModel,
    TarefaModel,
    WorkflowItemModel,
)
from modules.gestao_pessoal.application.antiguidade import (
    antiguidade_sort_key,
    is_ativo_na_om,
    normalize_text,
)
from modules.gestao_pessoal.application.deletion_archive import build_militar_deletion_archive
from modules.gestao_pessoal.application.hierarchy_config import load_hierarchy_config
from modules.gestao_pessoal.application.schemas import MilitarCreate, MilitarUpdate


class GestaoPessoalRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        query: str | None = None,
        limit: int = 100,
        include_inactive: bool = False,
        only_inactive: bool = False,
        posto_graduacao: str | None = None,
        secao: str | None = None,
        divisao: str | None = None,
        view_scope: str = "efetivo_completo",
        user_context: dict | None = None,
    ):
        hierarchy_config = load_hierarchy_config()
        if view_scope == "usuario" and not hierarchy_config.auto_scope_enabled:
            view_scope = "efetivo_completo"

        stmt = self.db.query(MilitarModel)

        if only_inactive:
            stmt = stmt.filter(MilitarModel.ativo.is_(False))
        elif not include_inactive:
            stmt = stmt.filter(MilitarModel.ativo.is_(True))

        if query:
            q = f"%{query.strip()}%"
            stmt = stmt.filter(
                (MilitarModel.nome_completo.ilike(q)) |
                (MilitarModel.nome_guerra.ilike(q)) |
                (MilitarModel.identidade.ilike(q)) |
                (MilitarModel.cpf.ilike(q))
            )

        if view_scope == "usuario":
            if not user_context or not user_context.get("scope_available"):
                return []

            context_secao = user_context.get("secao")
            context_divisao = user_context.get("divisao")
            if context_secao:
                stmt = stmt.filter(MilitarModel.secao.ilike(f"%{context_secao.strip()}%"))
            if context_divisao:
                context_q = f"%{context_divisao.strip()}%"
                stmt = stmt.filter(self._division_filter(context_q, hierarchy_config.division_fields))
            if not context_secao and not context_divisao and user_context.get("militar_id"):
                stmt = stmt.filter(MilitarModel.id == user_context["militar_id"])

        if posto_graduacao:
            stmt = stmt.filter(MilitarModel.posto_graduacao.ilike(f"%{posto_graduacao.strip()}%"))
        if secao:
            stmt = stmt.filter(MilitarModel.secao.ilike(f"%{secao.strip()}%"))
        if divisao:
            divisao_q = f"%{divisao.strip()}%"
            stmt = stmt.filter(self._division_filter(divisao_q, hierarchy_config.division_fields))

        return sorted(
            stmt.all(),
            key=lambda item: antiguidade_sort_key(item, hierarchy_config),
        )[:limit]

    def get_user_operational_context(self, user: dict | None) -> dict:
        if not user:
            return self._empty_user_context("USUARIO_NAO_INFORMADO")

        profile_secao = str(user.get("secao") or "").strip()
        profile_divisao = str(user.get("divisao") or "").strip()
        if profile_secao or profile_divisao:
            return {
                "scope_available": True,
                "source": "USER_OPERATIONAL_PROFILE",
                "militar_id": None,
                "nome_completo": user.get("display_name"),
                "nome_guerra": user.get("nome_guerra"),
                "posto_graduacao": user.get("posto_graduacao"),
                "secao": profile_secao or None,
                "divisao": profile_divisao or None,
                "warnings": [],
            }

        candidates = [
            user.get("identidade"),
            user.get("nome_guerra"),
            user.get("username"),
            user.get("display_name"),
            user.get("email", "").split("@")[0] if user.get("email") else None,
        ]
        normalized_candidates = {normalize_text(value) for value in candidates if value}
        normalized_candidates.discard("")

        if not normalized_candidates:
            return self._empty_user_context("USUARIO_SEM_IDENTIFICADOR_OPERACIONAL")

        militares = self.db.query(MilitarModel).filter(MilitarModel.ativo.is_(True)).all()
        for militar in militares:
            identity_values = {
                normalize_text(getattr(militar, "nome_completo", None)),
                normalize_text(getattr(militar, "nome_guerra", None)),
                normalize_text(getattr(militar, "identidade", None)),
                normalize_text(getattr(militar, "cpf", None)),
                normalize_text(getattr(militar, "email", None)),
            }
            identity_values.discard("")
            if normalized_candidates & identity_values:
                return {
                    "scope_available": True,
                    "source": "GESTAO_PESSOAL_MATCH_BY_USER",
                    "militar_id": militar.id,
                    "nome_completo": militar.nome_completo,
                    "nome_guerra": militar.nome_guerra,
                    "posto_graduacao": militar.posto_graduacao,
                    "secao": militar.secao,
                    "divisao": self._militar_division_value(militar),
                    "warnings": [],
                }

        return self._empty_user_context("USUARIO_NAO_VINCULADO_A_MILITAR")

    def list_filter_options(self) -> dict:
        hierarchy_config = load_hierarchy_config()
        militares = self.db.query(MilitarModel).filter(MilitarModel.ativo.is_(True)).all()
        postos = sorted(
            {item.posto_graduacao.strip() for item in militares if item.posto_graduacao},
            key=lambda value: antiguidade_sort_key(
                _SortProxy(posto_graduacao=value),
                hierarchy_config,
            ),
        )
        secoes = sorted({item.secao.strip() for item in militares if item.secao})
        divisoes = sorted(
            {
                value.strip()
                for item in militares
                for value in self._militar_division_values(item, hierarchy_config.division_fields)
                if value
            },
        )
        return {
            "postos_graduacoes": postos,
            "secoes": secoes,
            "divisoes": divisoes,
        }

    @staticmethod
    def _division_filter(pattern: str, fields: list[str]):
        filters = []
        for field in fields or ["local_om", "om"]:
            column = getattr(MilitarModel, field, None)
            if column is not None:
                filters.append(column.ilike(pattern))
        return or_(*filters) if filters else MilitarModel.id.is_(None)

    @staticmethod
    def _militar_division_values(militar, fields: list[str]) -> list[str]:
        return [
            str(getattr(militar, field, "") or "")
            for field in fields or ["local_om", "om"]
            if getattr(militar, field, None)
        ]

    @classmethod
    def _militar_division_value(cls, militar) -> str | None:
        hierarchy_config = load_hierarchy_config()
        values = cls._militar_division_values(militar, hierarchy_config.division_fields)
        return values[0] if values else None

    @staticmethod
    def _empty_user_context(reason: str) -> dict:
        return {
            "scope_available": False,
            "source": "UNRESOLVED",
            "militar_id": None,
            "nome_completo": None,
            "nome_guerra": None,
            "posto_graduacao": None,
            "secao": None,
            "divisao": None,
            "warnings": [reason],
        }

    def list_efetivo_om(self, *, om: str | None = None, limit: int = 500) -> dict:
        hierarchy_config = load_hierarchy_config()
        stmt = self.db.query(MilitarModel)
        if om:
            stmt = stmt.filter(MilitarModel.om.ilike(f"%{om.strip()}%"))

        militares = sorted(
            stmt.all(),
            key=lambda item: antiguidade_sort_key(item, hierarchy_config),
        )[:limit]
        ativos = [militar for militar in militares if is_ativo_na_om(militar)]
        inativos = [militar for militar in militares if not is_ativo_na_om(militar)]
        return {
            "ativos_na_om": sorted(
                ativos,
                key=lambda item: antiguidade_sort_key(item, hierarchy_config),
            ),
            "inativos_na_om": sorted(
                inativos,
                key=lambda item: antiguidade_sort_key(item, hierarchy_config),
            ),
        }

    def get(self, militar_id: int):
        return (
            self.db.query(MilitarModel)
            .filter(MilitarModel.id == militar_id)
            .first()
        )

    def get_by_identidade(self, identidade: str):
        return (
            self.db.query(MilitarModel)
            .filter(MilitarModel.identidade == identidade)
            .first()
        )

    def get_by_cpf(self, cpf: str):
        return (
            self.db.query(MilitarModel)
            .filter(MilitarModel.cpf == cpf)
            .first()
        )

    def get_by_prec_cp(self, prec_cp: str):
        return (
            self.db.query(MilitarModel)
            .filter(MilitarModel.prec_cp == prec_cp)
            .first()
        )

    def get_by_nome(self, nome: str):
        query = (nome or "").strip()
        if not query:
            return None
        return (
            self.db.query(MilitarModel)
            .filter(MilitarModel.nome_completo.ilike(query))
            .order_by(MilitarModel.ficha_cadastro_importado_em.desc().nullslast())
            .first()
        )

    def find_for_compilador(
        self,
        *,
        identidade: str | None = None,
        nome: str | None = None,
        prec_cp: str | None = None,
    ):
        if identidade:
            militar = self.get_by_identidade(identidade.strip())
            if militar:
                return militar
        if prec_cp:
            militar = self.get_by_prec_cp(prec_cp.strip())
            if militar:
                return militar
        if nome:
            return self.get_by_nome(nome)
        return None

    def create(self, payload: MilitarCreate):
        model = MilitarModel(**payload.model_dump())
        self.db.add(model)
        self.db.flush()
        self.db.refresh(model)
        return model

    def deactivate(self, militar_id: int):
        model = self.get(militar_id)
        if not model:
            return None

        model.ativo = False
        self.db.flush()
        self.db.refresh(model)
        return model

    def reactivate(self, militar_id: int):
        model = self.get(militar_id)
        if not model:
            return None

        model.ativo = True
        self.db.flush()
        self.db.refresh(model)
        return model

    def delete_permanent(self, militar_id: int) -> dict | None:
        model = self.get(militar_id)
        if not model:
            return None

        archive = build_militar_deletion_archive(self.db, model)

        snapshot = {
            "id": model.id,
            "nome_completo": model.nome_completo,
            "nome_guerra": model.nome_guerra,
            "posto_graduacao": model.posto_graduacao,
            "identidade": model.identidade,
            "ativo": model.ativo,
            "archive_path": archive.path.relative_to(settings.base_dir).as_posix(),
            "archive_sha256": archive.sha256,
        }

        folha_ids = [
            item.id
            for item in self.db.query(FolhaAlteracaoModel.id)
            .filter(FolhaAlteracaoModel.militar_id == militar_id)
            .all()
        ]
        if folha_ids:
            self.db.query(FolhaEventoModel).filter(
                FolhaEventoModel.folha_id.in_(folha_ids),
            ).delete(synchronize_session=False)

        self.db.query(CTSMModel).filter(CTSMModel.militar_id == militar_id).delete(
            synchronize_session=False,
        )
        self.db.query(CalculoTempoServicoModel).filter(
            CalculoTempoServicoModel.militar_id == militar_id,
        ).delete(synchronize_session=False)
        self.db.query(FolhaAlteracaoModel).filter(
            FolhaAlteracaoModel.militar_id == militar_id,
        ).delete(synchronize_session=False)
        self.db.query(MilitarPeriodoServicoModel).filter(
            MilitarPeriodoServicoModel.militar_id == militar_id,
        ).delete(synchronize_session=False)
        self.db.query(SicapexEventoFuncionalModel).filter(
            SicapexEventoFuncionalModel.militar_id == militar_id,
        ).delete(synchronize_session=False)

        for model_class in (
            CompilerVariableSnapshotModel,
            CompilerFileModel,
            CompilerRunModel,
            SicapexImportFileModel,
            TarefaModel,
            WorkflowItemModel,
        ):
            self.db.query(model_class).filter(model_class.militar_id == militar_id).update(
                {"militar_id": None},
                synchronize_session=False,
            )

        self.db.delete(model)
        self.db.flush()
        return snapshot

    def update(self, militar_id: int, payload: MilitarUpdate):
        model = self.get(militar_id)
        if not model:
            return None

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(model, key, value)

        self.db.flush()
        self.db.refresh(model)
        return model


class _SortProxy:
    def __init__(self, *, posto_graduacao: str):
        self.posto_graduacao = posto_graduacao
        self.data_incorporacao = None
        self.data_nascimento = None
        self.nome_completo = posto_graduacao
