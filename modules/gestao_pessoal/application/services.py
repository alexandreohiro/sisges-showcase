from datetime import date
from modules.gestao_pessoal.domain.entities import Militar


class GestaoPessoalService:
    def __init__(self) -> None:
        self._militares = [
            Militar(
                id_interno="mil_0001",
                nome_completo="CARLOS ALBERTO RONCONE",
                nome_guerra="RONCONE",
                graduacao="SUBTENENTE",
                identidade="043507214-5",
                qm="ARTILHARIA",
                om="B ADM QGEX",
                guarnicao="BRASÍLIA",
                data_de_praca=date(1997, 8, 6),
            ),
            Militar(
                id_interno="mil_0002",
                nome_completo="DIEGO MARTINS DE SOUSA",
                nome_guerra="SOUSA",
                graduacao="1º SGT",
                identidade="040040815-9",
                qm="CAVALARIA",
                om="B ADM QGEX",
                guarnicao="BRASÍLIA",
                data_de_praca=date(2008, 3, 1),
            ),
        ]

    def listar_pessoas(self) -> list[Militar]:
        return list(self._militares)

    def buscar_por_identidade(self, identidade: str) -> Militar | None:
        identidade = identidade.strip()
        for militar in self._militares:
            if militar.identidade == identidade:
                return militar
        return None

    def buscar_por_nome(self, termo: str) -> list[Militar]:
        termo = termo.strip().upper()
        return [m for m in self._militares if termo in m.nome_completo.upper()]

    def upsert_por_identidade(
        self,
        identidade: str,
        nome_completo: str = "",
        nome_guerra: str = "",
        graduacao: str = "",
        qm: str = "",
        data_de_praca: str = "",
    ) -> Militar:
        militar = self.buscar_por_identidade(identidade)

        if militar:
            if nome_completo:
                militar.nome_completo = nome_completo
            if nome_guerra:
                militar.nome_guerra = nome_guerra
            if graduacao:
                militar.graduacao = graduacao
            if qm:
                militar.qm = qm
            if data_de_praca:
                ano, mes, dia = map(int, data_de_praca.split("-"))
                militar.data_de_praca = date(ano, mes, dia)
            return militar

        novo = Militar(
            id_interno=f"mil_{len(self._militares)+1:04d}",
            nome_completo=nome_completo or "PENDENTE",
            nome_guerra=nome_guerra,
            graduacao=graduacao,
            identidade=identidade,
            qm=qm,
            om="",
            guarnicao="",
            data_de_praca=date.fromisoformat(data_de_praca) if data_de_praca else date(1900, 1, 1),
        )
        self._militares.append(novo)
        return novo