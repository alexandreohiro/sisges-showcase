from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdentidadeMilitar:
    valor: str

    def normalizada(self) -> str:
        return self.valor.strip()


@dataclass(frozen=True, slots=True)
class QualificacaoMilitar:
    valor: str

    def normalizada(self) -> str:
        return self.valor.strip().upper()