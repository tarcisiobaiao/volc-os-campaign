"""Resolvedor de identidade de campanha com nível de confiança e validade temporal.

Regra central: um `campaign.id` numérico resolve de forma determinística SOMENTE se
casar com exatamente uma campanha registrada (conta + id) válida no dia. Nome/slug
textual só resolve de forma probabilística, por mapa declarado e datado, e nunca quando
dois nomes colidem depois da normalização do sensor. Nada é criado por inferência.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from .chave_campanha import ChaveCampanha, MotivoRecusa
from .graos import Confianca
from .normalizacao import normalizar_utm_sensor_v3


class TemplateCampanha(str, enum.Enum):
    ID = "id"  # utm_campaign={campaignid}
    NOME = "nome"  # utm_campaign=<nome/slug> (Meta, campanhas manuais antigas)


@dataclass(frozen=True)
class CampanhaRegistrada:
    customer_id: str
    campaign_id: str
    nome: str
    valido_de: date
    valido_ate: Optional[date] = None  # inclusive; None = vigente
    template: TemplateCampanha = TemplateCampanha.ID

    def vale_em(self, dia: date) -> bool:
        return self.valido_de <= dia and (self.valido_ate is None or dia <= self.valido_ate)

    @property
    def chave_textual(self) -> str:
        return normalizar_utm_sensor_v3(self.nome)


@dataclass(frozen=True)
class Resolucao:
    confianca: Confianca
    motivo: str
    customer_id: Optional[str] = None
    campaign_id: Optional[str] = None

    def __post_init__(self) -> None:
        tem_id = self.campaign_id is not None
        if tem_id != (self.confianca is not Confianca.NAO_ATRIBUIVEL):
            raise ValueError("só resolução atribuível carrega campaign_id")

    @property
    def atribuivel(self) -> bool:
        return self.confianca is not Confianca.NAO_ATRIBUIVEL


@dataclass
class RegistroCampanhas:
    campanhas: list[CampanhaRegistrada] = field(default_factory=list)

    def adicionar(self, c: CampanhaRegistrada) -> None:
        self.campanhas.append(c)

    def por_id(self, campaign_id: str, dia: date) -> list[CampanhaRegistrada]:
        return [c for c in self.campanhas if c.campaign_id == campaign_id and c.vale_em(dia)]

    def por_texto(self, chave_textual: str, dia: date) -> list[CampanhaRegistrada]:
        return [c for c in self.campanhas
                if c.template is TemplateCampanha.NOME and c.vale_em(dia) and c.chave_textual == chave_textual]

    def resolver(self, chave: ChaveCampanha, dia: date) -> Resolucao:
        if chave.resolvida:
            achadas = self.por_id(chave.campaign_id, dia)
            contas = {c.customer_id for c in achadas}
            if len(contas) == 1:
                c = achadas[0]
                return Resolucao(Confianca.DETERMINISTICA, "id_numerico_registrado", c.customer_id, c.campaign_id)
            if len(contas) > 1:
                return Resolucao(Confianca.NAO_ATRIBUIVEL, "id_em_mais_de_uma_conta")
            return Resolucao(Confianca.NAO_ATRIBUIVEL, "id_nao_registrado_no_dia")
        if chave.recusa in (MotivoRecusa.TEXTUAL_AMBIGUO, MotivoRecusa.POSSIVELMENTE_TRUNCADO) and chave.valor_textual:
            achadas = self.por_texto(chave.valor_textual, dia)
            ids = {(c.customer_id, c.campaign_id) for c in achadas}
            if len(ids) == 1 and chave.recusa is MotivoRecusa.TEXTUAL_AMBIGUO:
                c = achadas[0]
                return Resolucao(Confianca.PROBABILISTICA, "nome_declarado_normalizado", c.customer_id, c.campaign_id)
            if len(ids) > 1:
                return Resolucao(Confianca.NAO_ATRIBUIVEL, "colisao_textual")
            if len(ids) == 1:
                return Resolucao(Confianca.NAO_ATRIBUIVEL, "texto_truncado_no_limite")
            return Resolucao(Confianca.NAO_ATRIBUIVEL, "texto_sem_mapa_declarado")
        return Resolucao(Confianca.NAO_ATRIBUIVEL, chave.recusa.value if chave.recusa else "sem_chave")


def registro_de(campanhas: Iterable[CampanhaRegistrada]) -> RegistroCampanhas:
    return RegistroCampanhas(list(campanhas))
