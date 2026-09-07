"""Contrato estrito do Assistente de Criativos Meta.

O LLM propõe; este módulo decide se a resposta tem forma suficiente para
entrar no sistema. IDs de provedor, mídia e campanha não pertencem aqui.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"
MAX_VARIACOES = 15


class ModeloEstrito(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Fase(str, Enum):
    NOVA_OPERACAO = "NOVA_OPERACAO"
    DIAGNOSTICO = "DIAGNOSTICO"
    ARQUITETURA = "ARQUITETURA"
    MATRIZ = "MATRIZ"
    COPY = "COPY"
    REFACAO = "REFACAO"


class EscopoFeedback(str, Enum):
    PONTUAL = "PONTUAL"
    GRUPO = "GRUPO"
    PROJETO = "PROJETO"
    UNIVERSAL = "UNIVERSAL"


class FatoDaOferta(ModeloEstrito):
    ref: str = Field(pattern=r"^fact_[a-z0-9_-]{3,64}$")
    declaracao: str = Field(min_length=3, max_length=1200)
    origem: Literal["LANDING_PAGE", "OPERADOR", "POLICY_RECEIPT", "PERFORMANCE_RECEIPT"]
    evidencia_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )


class Restricao(ModeloEstrito):
    ref: str = Field(pattern=r"^rule_[a-z0-9_-]{3,64}$")
    texto: str = Field(min_length=3, max_length=1000)
    escopo: EscopoFeedback = EscopoFeedback.PROJETO
    termos_bloqueados: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("termos_bloqueados")
    @classmethod
    def termos_validos(cls, value: list[str]) -> list[str]:
        limpos = [termo.strip() for termo in value]
        if any(len(termo) < 2 or len(termo) > 100 for termo in limpos):
            raise ValueError("termos_bloqueados devem ter entre 2 e 100 caracteres")
        if len({termo.casefold() for termo in limpos}) != len(limpos):
            raise ValueError("termos_bloqueados contém duplicatas")
        return limpos


class ElementoCongelado(ModeloEstrito):
    ref: str = Field(pattern=r"^frozen_[a-z0-9_-]{3,64}$")
    caminho: str = Field(min_length=3, max_length=180)
    valor: str = Field(min_length=1, max_length=4000)
    aprovado_em: str = Field(min_length=10, max_length=40)


class PedidoDoAgente(ModeloEstrito):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    fase: Fase = Fase.NOVA_OPERACAO
    project_ref: str = Field(pattern=r"^crproj_[a-f0-9]{24}$")
    nome_da_operacao: str = Field(min_length=3, max_length=200)
    brand_pack_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )
    destination_ref: str = Field(pattern=r"^[A-Za-z0-9:_-]{3,180}$")
    objetivo_meta: str = Field(min_length=3, max_length=64)
    pais: str = Field(default="BR", pattern=r"^[A-Z]{2}$")
    idioma: str = Field(default="pt-BR", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    contexto_do_publico: str = Field(min_length=3, max_length=4000)
    fatos_da_oferta: list[FatoDaOferta] = Field(min_length=1, max_length=80)
    restricoes: list[Restricao] = Field(default_factory=list, max_length=80)
    elementos_congelados: list[ElementoCongelado] = Field(default_factory=list, max_length=100)
    formatos_permitidos: list[str] = Field(default_factory=lambda: ["1x1", "4x5", "9x16"], min_length=1, max_length=12)
    quantidade_de_pecas: int = Field(default=6, ge=1, le=MAX_VARIACOES)
    feedback: str | None = Field(default=None, max_length=4000)
    feedback_escopo: EscopoFeedback | None = None
    #: O lote que a run anterior produziu, quando existe.
    #:
    #: Refinar sem ele é reescrever do zero: o modelo recebia briefing, feedback
    #: e elementos congelados, mas NÃO o que ele mesmo tinha proposto — então
    #: "troque o hook da peça do frio" não tinha peça nenhuma para trocar, e a
    #: run devolvia um lote novo que só coincidia com o anterior nos pontos
    #: congelados. O campo é montado no servidor a partir da última run
    #: concluída; o cliente não o envia e não pode forjá-lo.
    saida_anterior: "SaidaDoAgente | None" = None

    @field_validator("formatos_permitidos")
    @classmethod
    def formatos_unicos(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("formatos_permitidos contém duplicatas")
        return value

    @model_validator(mode="after")
    def feedback_com_escopo(self) -> "PedidoDoAgente":
        if bool(self.feedback) != bool(self.feedback_escopo):
            raise ValueError("feedback e feedback_escopo devem ser enviados juntos")
        refs = [f.ref for f in self.fatos_da_oferta]
        if len(refs) != len(set(refs)):
            raise ValueError("fatos_da_oferta contém refs duplicadas")
        if self.fase == Fase.REFACAO and not self.feedback:
            raise ValueError("REFACAO exige feedback escopado")
        return self


class EntradaNovaOperacao(ModeloEstrito):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    nome_da_operacao: str = Field(min_length=3, max_length=200)
    brand_pack_ref: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9:_-]{3,180}$"
    )
    destination_ref: str = Field(pattern=r"^[A-Za-z0-9:_-]{3,180}$")
    objetivo_meta: str = Field(min_length=3, max_length=64)
    pais: str = Field(default="BR", pattern=r"^[A-Z]{2}$")
    idioma: str = Field(default="pt-BR", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    contexto_do_publico: str = Field(min_length=3, max_length=4000)
    fatos_da_oferta: list[FatoDaOferta] = Field(min_length=1, max_length=80)
    restricoes: list[Restricao] = Field(default_factory=list, max_length=80)
    formatos_permitidos: list[str] = Field(default_factory=lambda: ["1x1", "4x5", "9x16"], min_length=1, max_length=12)
    quantidade_de_pecas: int = Field(default=6, ge=1, le=MAX_VARIACOES)

    @field_validator("formatos_permitidos")
    @classmethod
    def formatos_unicos(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("formatos_permitidos contém duplicatas")
        return value


class PedidoDeContinuacao(ModeloEstrito):
    fase: Fase
    quantidade_de_pecas: int | None = Field(default=None, ge=1, le=MAX_VARIACOES)
    formatos_permitidos: list[str] | None = Field(default=None, min_length=1, max_length=12)
    feedback: str | None = Field(default=None, max_length=4000)
    feedback_escopo: EscopoFeedback | None = None

    @model_validator(mode="after")
    def feedback_com_escopo(self) -> "PedidoDeContinuacao":
        if bool(self.feedback) != bool(self.feedback_escopo):
            raise ValueError("feedback e feedback_escopo devem ser enviados juntos")
        if self.fase == Fase.REFACAO and not self.feedback:
            raise ValueError("REFACAO exige feedback escopado")
        return self


class PedidoDeDecisao(ModeloEstrito):
    run_ref: str = Field(pattern=r"^crrun_[a-f0-9]{24}$")
    decisao: Literal["APROVADO", "REPROVADO"]
    escopo: EscopoFeedback
    caminho: str = Field(pattern=r"^/(?:[A-Za-z0-9_-]+/?)+$", max_length=300)
    feedback: str | None = Field(default=None, max_length=4000)


class Diagnostico(ModeloEstrito):
    oferta_real: str = Field(min_length=3, max_length=1500)
    promessa_maxima: str = Field(min_length=3, max_length=1000)
    tensao_central: str = Field(min_length=3, max_length=1000)
    desconhecidos: list[str] = Field(default_factory=list, max_length=30)
    fato_refs: list[str] = Field(min_length=1, max_length=30)


class EstadoMental(ModeloEstrito):
    ref: str = Field(pattern=r"^state_[a-z0-9_-]{3,64}$")
    nome: str = Field(min_length=3, max_length=160)
    ja_sabe: str = Field(min_length=3, max_length=600)
    duvida: str = Field(min_length=3, max_length=600)
    tensao: str = Field(min_length=3, max_length=600)
    proximo_movimento: str = Field(min_length=3, max_length=600)


class GrupoEstrategico(ModeloEstrito):
    ref: str = Field(pattern=r"^group_[a-z0-9_-]{3,64}$")
    nome: str = Field(min_length=3, max_length=160)
    estado_mental_refs: list[str] = Field(min_length=1, max_length=12)
    funcao: str = Field(min_length=3, max_length=600)
    territorio: str = Field(min_length=3, max_length=600)
    diferenca_material: str = Field(min_length=3, max_length=600)


class CopyCompartilhada(ModeloEstrito):
    ref: str = Field(pattern=r"^copy_[a-z0-9_-]{3,64}$")
    group_ref: str = Field(pattern=r"^group_[a-z0-9_-]{3,64}$")
    texto_principal: str = Field(min_length=1, max_length=2200)
    titulo: str = Field(min_length=1, max_length=255)
    descricao: str = Field(min_length=1, max_length=255)
    cta_nativa: Literal["LEARN_MORE", "SIGN_UP", "GET_QUOTE", "APPLY_NOW", "CONTACT_US", "DOWNLOAD"] = "LEARN_MORE"
    narracao: str | None = Field(default=None, max_length=1200)
    fato_refs: list[str] = Field(min_length=1, max_length=30)


class PecaCriativa(ModeloEstrito):
    ref: str = Field(pattern=r"^creative_[a-z0-9_-]{3,64}$")
    group_ref: str = Field(pattern=r"^group_[a-z0-9_-]{3,64}$")
    shared_copy_ref: str = Field(pattern=r"^copy_[a-z0-9_-]{3,64}$")
    estado_mental_ref: str = Field(pattern=r"^state_[a-z0-9_-]{3,64}$")
    angulo: str = Field(min_length=3, max_length=300)
    subangulo: str = Field(min_length=3, max_length=300)
    hipotese: str = Field(min_length=3, max_length=700)
    hook: str = Field(min_length=3, max_length=300)
    mecanismo_de_interrupcao: str = Field(min_length=3, max_length=300)
    formato: str = Field(min_length=2, max_length=80)
    headline_interna: str = Field(min_length=1, max_length=160)
    complemento_interno: str | None = Field(default=None, max_length=300)
    cta_visual: str | None = Field(default=None, max_length=60)
    direcao_visual: str = Field(min_length=3, max_length=1200)
    fato_refs: list[str] = Field(min_length=1, max_length=30)
    rule_refs: list[str] = Field(default_factory=list, max_length=30)


class ReciboDeValidacao(ModeloEstrito):
    valido: bool
    codigos: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    knowledge_base_version: str = "copiloto-meta-ads-v2-derived@1.0"


class SaidaDoAgente(ModeloEstrito):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_ref: str = Field(pattern=r"^crproj_[a-f0-9]{24}$")
    fase_concluida: Fase
    diagnostico: Diagnostico
    jornada: list[EstadoMental] = Field(min_length=1, max_length=20)
    grupos: list[GrupoEstrategico] = Field(min_length=1, max_length=12)
    copies_compartilhadas: list[CopyCompartilhada] = Field(min_length=1, max_length=24)
    pecas: list[PecaCriativa] = Field(min_length=1, max_length=MAX_VARIACOES)
    recibo: ReciboDeValidacao = Field(
        default_factory=lambda: ReciboDeValidacao(valido=False)
    )
    proximo_ato: str = Field(min_length=3, max_length=500)


_METADADO_NA_PECA = re.compile(
    r"\b(?:G\d+-C\d+|V\d+|APROVAD[OA]|REPROVAD[OA]|STATUS\s*[:=]|GRUPO\s+\d+)\b",
    re.IGNORECASE,
)


def campos_textuais_da_peca(peca: PecaCriativa) -> str:
    return " ".join(
        filter(None, [peca.headline_interna, peca.complemento_interno, peca.cta_visual])
    )


def contem_metadado_operacional(peca: PecaCriativa) -> bool:
    return bool(_METADADO_NA_PECA.search(campos_textuais_da_peca(peca)))


# `PedidoDoAgente.saida_anterior` referencia `SaidaDoAgente`, que nasce mais
# abaixo neste módulo. A reconstrução resolve a referência adiante sem inverter
# a ordem de leitura do arquivo, que vai do pedido para a saída de propósito.
PedidoDoAgente.model_rebuild()
