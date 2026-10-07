"""O CONTRATO DE MEDIÇÃO que um funil com jornada emite (07/10/2026).

Não é tracking: nada aqui coleta, envia ou grava evento. É o artefato tipado
que diz O QUE precisaria ser medido para validar (ou derrubar) as hipóteses do
desenho, de qual contrato existente cada sinal sairia, e — quando houver
leitura — de que NATUREZA ela é.

Três naturezas, e a separação é estrutural, não convenção:

- `hipotese`        -> o que o arquiteto supõe. Sem número.
- `simulacao`       -> o que um simulador estimou (ex.: MiroFish). Só FAIXA
                       qualitativa; um número aqui seria lido como métrica.
- `observacao_real` -> evento ou relatório real, com fonte, janela e amostra.

Uma simulação NÃO consegue entrar como observação: a fonte `simulacao:*` é
recusada em `observacao_real`, e um `valor` numérico é recusado em tudo que
não for observação. É o caso [C10] da missão.

O feedback produz uma PROPOSTA de nova versão para aprovação humana — os dois
literais de `PropostaDeNovaVersao` tornam impossível representar o contrário.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from funnelforge.domain.models import (
    ClassificacaoDeSaida,
    EvidenciaDaJornada,
    JanelaDeColeta,
    NaturezaDoDado,
    canon_rotulo,
    fonte_nao_observada,
)

SINAIS: tuple[str, ...] = (
    "chegada_lp", "escolha_de_ramo", "progressao", "resolucao",
    "saida_oficial_boa", "saida_oficial_prematura", "loop_revisita",
    "abandono", "receita_por_sessao", "rpm_valor_de_sessao", "core_web_vitals",
)
Sinal = Literal[
    "chegada_lp", "escolha_de_ramo", "progressao", "resolucao",
    "saida_oficial_boa", "saida_oficial_prematura", "loop_revisita",
    "abandono", "receita_por_sessao", "rpm_valor_de_sessao", "core_web_vitals",
]


class SinalPrevisto(BaseModel):
    """Um sinal que o funil PRECISA para ser julgado, ligado a um contrato que
    já existe (ou dito como não implantado). `escopo`: `funil`,
    `pagina:<duvida>`, `aresta:<a>-><b>` ou `coorte:<canal>-><duvida>`."""
    sinal: Sinal
    escopo: str = Field(min_length=1)
    hipotese: str = Field(min_length=1)
    fonte_prevista: str = Field(min_length=1)
    coleta: Literal["nao_implantada", "existente_parcial", "existente"] = "nao_implantada"


class LeituraDoFunil(BaseModel):
    natureza: NaturezaDoDado
    sinal: Sinal
    escopo: str = Field(min_length=1)
    valor: float | None = None
    faixa: str | None = None
    fonte: str = Field(min_length=1)
    janela: JanelaDeColeta | None = None
    amostra: int | None = None
    # O identificador que alguém consegue reabrir: id do relatório, da consulta
    # GAQL, do export. Sem ele uma "observação" não é auditável.
    referencia: str = ""

    @field_validator("natureza", mode="before")
    @classmethod
    def _rotulo(cls, value: object) -> object:
        return canon_rotulo(value)

    @model_validator(mode="after")
    def _natureza_coerente(self) -> "LeituraDoFunil":
        if self.natureza == "observacao_real":
            # A MESMA guarda da evidência da jornada (`fonte_nao_observada`).
            if fonte_nao_observada(self.fonte):
                raise ValueError("observação real não pode vir de simulação ou hipótese")
            if (self.valor is None or self.janela is None or not self.amostra
                    or not self.referencia.strip()):
                raise ValueError(
                    "observação real exige valor, janela, amostra > 0 e referencia")
            return self
        if self.valor is not None:
            raise ValueError(
                f"leitura de natureza '{self.natureza}' não carrega número: use `faixa`")
        if self.natureza == "simulacao" and not self.fonte.strip().lower().startswith(
                "simulacao:"):
            raise ValueError("simulação precisa de fonte 'simulacao:<origem>'")
        return self


class MudancaSugerida(BaseModel):
    alvo: str = Field(min_length=1)          # duvida_id, aresta ou "funil"
    proposta: str = Field(min_length=1)
    motivo: str = Field(min_length=1)
    natureza_da_base: NaturezaDoDado


class PropostaDeNovaVersao(BaseModel):
    """O que o ciclo construir → medir → decidir → modificar devolve. Nunca é
    aplicada por código: os dois literais abaixo não admitem outro valor."""
    requer_aprovacao_humana: Literal[True] = True
    publicacao_automatica: Literal[False] = False
    base_observada: list[LeituraDoFunil] = []
    hipoteses_a_testar: list[str] = []
    mudancas_sugeridas: list[MudancaSugerida] = []

    @model_validator(mode="after")
    def _so_observacao_na_base(self) -> "PropostaDeNovaVersao":
        if any(l.natureza != "observacao_real" for l in self.base_observada):
            raise ValueError("base_observada só aceita observação real")
        return self


class ContratoDeMedicao(BaseModel):
    versao: Literal["medicao-jornada-v1"] = "medicao-jornada-v1"
    run_id: str
    sinais: list[SinalPrevisto] = []
    saidas_oficiais: dict[str, ClassificacaoDeSaida] = {}
    premissas: list[EvidenciaDaJornada] = []
    leituras: list[LeituraDoFunil] = []
    proposta: PropostaDeNovaVersao | None = None

    def observadas(self) -> list[LeituraDoFunil]:
        """Só o que é dado real. Simulação e hipótese nunca saem daqui."""
        return [l for l in self.leituras if l.natureza == "observacao_real"]
