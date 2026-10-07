"""INVENTÁRIO FACTUAL de uma página (reforma editorial, etapa B4).

É tudo o que o briefing PODE usar, e nada além: os fatos da pesquisa desta
página já tipados, as fontes com o selo de "respondeu a uma visita real", os
canais oficiais que a pesquisa escolheu, os termos de busca em três estados, a
leitura (perguntas reais e tensão medida) e o anúncio que traz o leitor à LP.

## Função pura, não modelo persistido

A verificação adversarial (V19) mostrou que um inventário gravado no estado é
adiável: ele é DERIVADO de `state.facts`, `state.official_links` e do plano.
Por isso `montar_inventario` recalcula, sem rede e sem LLM, e o passo do
briefing grava uma cópia em `runs/<id>/p{n}.inventario.json` só para auditoria.

## A regra de legado (state.json anterior à pesquisa tipada)

Fato sem `tipo` não é descartado nem renomeado em silêncio. Recebe o tipo por
uma regra conservadora sobre CAMPOS ESTRUTURADOS e fica marcado
`tipo_origem = "regra_legado"`. A regra mora em UM lugar, compartilhado com a
ponte do volc_ads: `domain/tipagem_de_fatos.py` (S2 · item 5).

## Termos de busca: filtro de dado pessoal ANTES de qualquer prompt

O que o leitor digitou pode trazer CPF, e-mail ou telefone. Esses termos saem
aqui, contados, e nunca chegam a um modelo. A amostra é limitada e declarada
("25 de 1.303"), e é sempre subconjunto do que a fonte trouxe.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel

from funnelforge.domain.models import (
    TIPOS_DE_FATO,
    Page,
    PageRole,
    ResearchFacts,
    RunState,
    canon_tipo_de_fato,
    effective_role,
)
from funnelforge.domain.tipagem_de_fatos import tipo_pela_regra_de_legado

# Quantos termos de busca vão ao prompt, no máximo (os mais clicados).
LIMITE_DE_TERMOS = 25

_DADO_PESSOAL_RES = (
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),          # CPF
    re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),     # CNPJ
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                      # e-mail
    re.compile(r"(?:\d[\s.\-]?){10,}"),                          # telefone, cartão
)


class FatoDoInventario(BaseModel):
    id: str
    tipo: str
    tipo_origem: Literal["pesquisa", "regra_legado"]
    origem: Literal["fatos_verificados", "dados_validados"]
    texto: str
    fonte: str = ""
    dispositivo: str = ""
    vigente_desde: date | None = None
    # A fonte primária respondeu à visita ao vivo? Só fato verificado ao vivo
    # autoriza cifra no texto (mesma régua do `critical_fact_grounding`).
    verificada_ao_vivo: bool = False
    escopo: str | None = None
    citavel: bool | None = None


class FonteDoInventario(BaseModel):
    id: str
    url: str
    papel: Literal["oficial", "secundaria"]
    resolvida: bool


class TermosNoInventario(BaseModel):
    estado: Literal["presente", "vazio_confirmado", "ausente"]
    janela: str = ""
    fonte: str = ""
    coletado_em: str = ""
    amostra: list[str] = []
    amostra_detalhe: list[dict] = []
    total_na_fonte: int = 0
    descartados_por_dado_pessoal: int = 0
    motivo_ausencia: str | None = None


class LeituraNoInventario(BaseModel):
    estado: Literal["presente", "ausente"]
    perguntas_paa: list[str] = []
    tensao: dict | None = None
    motivo_ausencia: str | None = None


class AnuncioNoInventario(BaseModel):
    estado: Literal["presente", "ausente"]
    titulos: list[str] = []
    descricoes: list[str] = []
    fonte: str = ""
    motivo_ausencia: str | None = None


class InventarioFactual(BaseModel):
    versao: str = "inventario-v1"
    pagina: int
    fatos: list[FatoDoInventario] = []
    fontes: list[FonteDoInventario] = []
    canais_oficiais: list[str] = []
    termos_de_busca: TermosNoInventario
    leitura: LeituraNoInventario
    anuncio: AnuncioNoInventario


def _tipado(declarado: object, origem: str, unidade: str = "") -> tuple[str, str]:
    tipo = canon_tipo_de_fato(declarado)
    if tipo in TIPOS_DE_FATO:
        return tipo, "pesquisa"
    return tipo_pela_regra_de_legado(origem, unidade), "regra_legado"


def _fatos(facts: ResearchFacts) -> list[FatoDoInventario]:
    resolvidas = set(facts.fontes_resolvidas or [])
    saida: list[FatoDoInventario] = []
    for i, dado in enumerate(facts.dados_validados or [], start=1):
        if not isinstance(dado, dict):
            continue
        texto = str(dado.get("fato") or "").strip()
        if not texto:
            continue
        tipo, origem_do_tipo = _tipado(dado.get("tipo"), "dados_validados")
        citavel = dado.get("citavel")
        saida.append(FatoDoInventario(
            id=f"f{i}", tipo=tipo, tipo_origem=origem_do_tipo, origem="dados_validados",
            texto=texto, fonte=str(dado.get("fonte") or "").strip(),
            verificada_ao_vivo=False, escopo=dado.get("escopo"),
            citavel=citavel if isinstance(citavel, bool) else None,
        ))
    for i, fato in enumerate(facts.fatos_verificados or [], start=1):
        tipo, origem_do_tipo = _tipado(fato.tipo, "fatos_verificados", fato.unidade)
        saida.append(FatoDoInventario(
            id=f"n{i}", tipo=tipo, tipo_origem=origem_do_tipo, origem="fatos_verificados",
            # valor + ESPAÇO + unidade: colados, viravam "2salários mínimos" (V8)
            texto=f"{fato.valor.strip()} {fato.unidade.strip()}".strip(),
            fonte=fato.fonte_primaria, dispositivo=fato.dispositivo,
            vigente_desde=fato.vigente_desde,
            verificada_ao_vivo=fato.fonte_primaria in resolvidas,
            escopo=fato.escopo, citavel=fato.citavel,
        ))
    return saida


def _fontes(facts: ResearchFacts, canais: list[str]) -> list[FonteDoInventario]:
    ordem = list(facts.fontes or [])
    ordem += [f.fonte_primaria for f in (facts.fatos_verificados or [])]
    ordem += [str(d.get("fonte") or "") for d in (facts.dados_validados or [])
              if isinstance(d, dict)]
    resolvidas = set(facts.fontes_resolvidas or [])
    oficiais = {c.rstrip("/") for c in canais}
    vistas: set[str] = set()
    saida: list[FonteDoInventario] = []
    for bruto in ordem:
        url = (bruto or "").strip()
        if not url.startswith(("http://", "https://")) or url in vistas:
            continue
        vistas.add(url)
        saida.append(FonteDoInventario(
            id=f"s{len(saida) + 1}", url=url,
            papel="oficial" if url.rstrip("/") in oficiais else "secundaria",
            resolvida=url in resolvidas,
        ))
    return saida


def tem_dado_pessoal(termo: str) -> bool:
    return any(r.search(termo or "") for r in _DADO_PESSOAL_RES)


def _termos(state: RunState) -> TermosNoInventario:
    plano = state.plan
    contexto = plano.contexto_de_busca if plano is not None else None
    if contexto is None:
        return TermosNoInventario(
            estado="ausente",
            motivo_ausencia=("o funnel_architecture não trouxe contexto_de_busca "
                             "(funil novo não tem campanha)"))
    if contexto.estado == "ausente":
        return TermosNoInventario(
            estado="ausente",
            motivo_ausencia=contexto.motivo_ausencia or "sem motivo informado")
    janela = contexto.janela
    rotulo_janela = (f"{janela.inicio.isoformat()} a {janela.fim.isoformat()} ({janela.fuso})"
                     if janela is not None else "")
    limpos = [t for t in contexto.termos if not tem_dado_pessoal(t.termo)]
    ordenados = sorted(limpos, key=lambda t: (-t.cliques, -t.impressoes, t.termo))
    amostra = ordenados[:LIMITE_DE_TERMOS]
    return TermosNoInventario(
        estado=contexto.estado, janela=rotulo_janela, fonte=contexto.fonte or "",
        coletado_em=contexto.coletado_em or "",
        amostra=[t.termo for t in amostra],
        amostra_detalhe=[{"termo": t.termo, "cliques": t.cliques, "impressoes": t.impressoes}
                         for t in amostra],
        total_na_fonte=len(contexto.termos),
        descartados_por_dado_pessoal=len(contexto.termos) - len(limpos),
    )


def _leitura(state: RunState) -> LeituraNoInventario:
    plano = state.plan
    leitura = plano.contexto_de_leitura if plano is not None else None
    if leitura is None or not (leitura.perguntas_paa or leitura.tensao):
        return LeituraNoInventario(
            estado="ausente",
            motivo_ausencia="o funnel_architecture não trouxe contexto_de_leitura")
    return LeituraNoInventario(
        estado="presente", perguntas_paa=list(leitura.perguntas_paa),
        tensao=(leitura.tensao.model_dump() if leitura.tensao is not None else None))


def _anuncio(state: RunState, page: Page) -> AnuncioNoInventario:
    if effective_role(page) is not PageRole.LP:
        return AnuncioNoInventario(
            estado="ausente",
            motivo_ausencia="página interna: o leitor chega pelo funil, não pelo anúncio")
    plano = state.plan
    anuncio = plano.contexto_de_anuncio if plano is not None else None
    if anuncio is None:
        return AnuncioNoInventario(
            estado="ausente",
            motivo_ausencia="o funnel_architecture não trouxe contexto_de_anuncio")
    return AnuncioNoInventario(
        estado=anuncio.estado, titulos=list(anuncio.titulos),
        descricoes=list(anuncio.descricoes), fonte=anuncio.fonte,
        motivo_ausencia=anuncio.motivo_ausencia)


def montar_inventario(state: RunState, page: Page) -> InventarioFactual:
    """O inventário factual desta página. Puro: sem rede, sem LLM, sem gravar."""
    facts = state.facts.get(page.page_number) or ResearchFacts(sparse=True)
    canais = list(state.official_links.get(page.page_number, []) or [])
    return InventarioFactual(
        pagina=page.page_number,
        fatos=_fatos(facts),
        fontes=_fontes(facts, canais),
        canais_oficiais=canais,
        termos_de_busca=_termos(state),
        leitura=_leitura(state),
        anuncio=_anuncio(state, page),
    )
