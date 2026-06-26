from infra.persistence.models import MilitarModel
from modules.gestao_pessoal.infrastructure.repository import GestaoPessoalRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import infra.persistence.models  # noqa: F401
from infra.persistence.db import Base


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_find_for_compilador_by_identidade():
    db_session = _session()
    militar = MilitarModel(
        nome_completo="MILITAR TESTE CONTEXTO",
        identidade="1122334455",
        prec_cp="998877",
        ativo=True,
    )
    db_session.add(militar)
    db_session.flush()

    found = GestaoPessoalRepository(db_session).find_for_compilador(
        identidade="1122334455",
    )

    assert found.id == militar.id


def test_find_for_compilador_by_prec_cp():
    db_session = _session()
    militar = MilitarModel(
        nome_completo="MILITAR TESTE PREC",
        identidade="2233445566",
        prec_cp="PREC123",
        ativo=True,
    )
    db_session.add(militar)
    db_session.flush()

    found = GestaoPessoalRepository(db_session).find_for_compilador(
        prec_cp="PREC123",
    )

    assert found.id == militar.id


def test_find_for_compilador_by_nome():
    db_session = _session()
    militar = MilitarModel(
        nome_completo="MILITAR TESTE NOME",
        identidade="3344556677",
        ativo=True,
    )
    db_session.add(militar)
    db_session.flush()

    found = GestaoPessoalRepository(db_session).find_for_compilador(
        nome="MILITAR TESTE NOME",
    )

    assert found.id == militar.id


def test_list_hides_inactive_by_default_and_can_include_inactive():
    db_session = _session()
    active = MilitarModel(nome_completo="MILITAR ATIVO", identidade="4455667788", ativo=True)
    inactive = MilitarModel(
        nome_completo="MILITAR INATIVO",
        identidade="5566778899",
        ativo=False,
    )
    db_session.add_all([active, inactive])
    db_session.flush()

    repo = GestaoPessoalRepository(db_session)

    assert [item.nome_completo for item in repo.list()] == ["MILITAR ATIVO"]
    assert [item.nome_completo for item in repo.list(include_inactive=True)] == [
        "MILITAR ATIVO",
        "MILITAR INATIVO",
    ]


def test_deactivate_and_reactivate_preserve_record():
    db_session = _session()
    militar = MilitarModel(
        nome_completo="MILITAR SOFT DELETE",
        identidade="6677889900",
        ativo=True,
    )
    db_session.add(militar)
    db_session.flush()

    repo = GestaoPessoalRepository(db_session)

    deactivated = repo.deactivate(militar.id)
    assert deactivated is not None
    assert deactivated.id == militar.id
    assert deactivated.ativo is False

    reactivated = repo.reactivate(militar.id)
    assert reactivated is not None
    assert reactivated.id == militar.id
    assert reactivated.ativo is True
