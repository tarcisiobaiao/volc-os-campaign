"""O DOSSIÊ FACTUAL do funil: um artefato canônico por run (`dossie_factual.json`).

Não é uma segunda arquitetura factual. É a COMPILAÇÃO tipada do que o motor já
tem — jornada (pergunta, promessa, entregas, estado do leitor, saída oficial,
plano visual, ativos), fatos tipados da pesquisa, verificação ao vivo das
fontes e canais oficiais — num pacote fechado por página, com cobertura e hash.

Regra que este contrato carrega: confiança do modelo não é prova. Um fato só é
`verified` quando a fonte foi CITADA pelo grounding do provedor e RESPONDEU na
verificação ao vivo; número, prazo e data ainda exigem referência temporal.
Divergência entre fontes para o mesmo requisito vira `conflict` e bloqueia.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

VERSAO_DO_DOSSIE = "dossie-factual-v1"

StatusDoFato = Literal["verified", "unverified", "conflict"]
TipoDaFonte = Literal["oficial", "canal_oficial", "secundaria"]

#: Tipos de fato que exigem referência temporal (vigência e data de verificação).
TIPOS_TEMPORAIS = frozenset({"numero", "prazo", "data", "mudanca"})


class FatoDoDossie(BaseModel):
    fact_id: str = Field(pattern=r"^f_[0-9a-f]{12}$")
    afirmacao: str = Field(min_length=1)
    tipo: str
    valor: str = ""
    unidade: str = ""
    source_url: str
    tipo_da_fonte: TipoDaFonte = "secundaria"
    verificado_em: date | None = None
    vigente_desde: date | None = None
    status: StatusDoFato = "unverified"
    motivo_do_status: str = ""
    paginas: list[str] = []            # duvida_ids que o fato pode sustentar
    requisitos: list[str] = []         # ids de RequisitoFactual que ele cobre
    evidencia: str = ""                # trecho curto ou referência verificável
    dispositivo: str = ""


class CoberturaDoRequisito(BaseModel):
    requisito_id: str
    coberto: bool
    fatos: list[str] = []
    motivo: str = ""


class CoberturaDaPagina(BaseModel):
    """O CoverageResult de uma página: cada requisito, e o veredito."""
    ready_to_write: bool = False
    requisitos: list[CoberturaDoRequisito] = []
    blockers: list[str] = []
    # Ativo -> fato que prova cada necessidade declarada (regra, valor vigente),
    # com a abrangência da fonte. E o que não achou fonte aceitável.
    vinculos: list[dict] = []
    vinculos_faltantes: list[dict] = []


class DossieDaPagina(BaseModel):
    """O PageDossier: o pacote fechado que redator e revisor recebem."""
    page_number: int
    slug: str
    role: str
    duvida_id: str
    pergunta: str
    promessa: str
    entregas: list[str] = []
    ja_resolvido: list[str] = []       # resolvido em TODO caminho até a página
    proxima_duvida: str = ""
    requisitos: list[str] = []         # ids obrigatórios
    fatos_verificados: list[str] = []  # fact_ids `verified` desta página
    fatos_nao_confirmados: list[str] = []
    conflitos: list[str] = []
    urls_oficiais: list[str] = []      # canais oficiais verificados desta página
    cta: dict = {}                     # destinos e classe da saída oficial
    layout: list[str] = []             # intenções do plano visual
    assets: list[str] = []             # ferramentas e prints possíveis
    cobertura: CoberturaDaPagina = CoberturaDaPagina()
    sha256: str = ""


class FonteDoDossie(BaseModel):
    url: str
    tipo_da_fonte: TipoDaFonte
    citada_pelo_grounding: bool
    verificada: bool
    motivo: str = ""


class TelemetriaDaPesquisa(BaseModel):
    rodada: int
    modelo_pedido: str
    modelo_servido: str
    auth_mode: str
    citacoes: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    custo_usd: float = 0.0
    latencia_ms: int = 0
    consultas_de_busca: int = 0        # grounding: cobrado por consulta, fora do custo
    finish_reason: str = ""
    chamadas: list[dict] = []          # metadados sanitizados de cada chamada
    faltantes_pedidos: list[str] = []


class DossieDoFunil(BaseModel):
    """O FunnelDossier: o único artefato factual canônico do run."""
    schema_version: Literal["dossie-factual-v1"] = VERSAO_DO_DOSSIE
    run_id: str
    assunto: str
    gerado_em: str
    fontes: list[FonteDoDossie] = []
    fatos: list[FatoDoDossie] = []
    paginas: list[DossieDaPagina] = []
    conflitos: list[str] = []
    lacunas: list[dict] = []           # {pagina, requisito, motivo}
    pesquisa: list[TelemetriaDaPesquisa] = []
    sha256: str = ""

    def pagina(self, numero: int) -> DossieDaPagina | None:
        return next((p for p in self.paginas if p.page_number == numero), None)

    def fatos_da_pagina(self, numero: int, *, so_verificados: bool = True) -> list[FatoDoDossie]:
        pg = self.pagina(numero)
        if pg is None:
            return []
        ids = set(pg.fatos_verificados) if so_verificados else (
            set(pg.fatos_verificados) | set(pg.fatos_nao_confirmados) | set(pg.conflitos))
        return [f for f in self.fatos if f.fact_id in ids]


_PALAVRAS_NUMERO = {"um": 1.0, "uma": 1.0, "dois": 2.0, "duas": 2.0, "tres": 3.0, "quatro": 4.0,
                    "cinco": 5.0, "seis": 6.0, "sete": 7.0, "oito": 8.0, "nove": 9.0, "dez": 10.0}


def texto_normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9,.$ ]+", " ", t)


def numeros_do_texto(texto: str) -> set[float]:
    """Os números de um texto pelo VALOR: '02' = '2' = 'dois'; '1,5' = '1.5';
    '3.242,00' = 3242."""
    alvo = texto_normal(texto)
    achados = set()
    for n in re.findall(r"\d+(?:[.,]\d+)*", alvo):
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", n):
            n = n.replace(".", "").replace(",", ".")
        else:
            n = n.replace(",", ".")
        try:
            achados.add(float(n))
        except ValueError:
            continue
    achados |= {v for p, v in _PALAVRAS_NUMERO.items() if re.search(rf"\b{p}\b", alvo)}
    return achados


def nucleo_da_unidade(unidade: str) -> str:
    """A dimensão da unidade: 'salários mínimos federais por pessoa' -> 'salarios'."""
    partes = texto_normal(unidade).split()
    return partes[0] if partes else ""


def json_canonico(dados: object) -> str:
    return json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str)


def sha256_canonico(dados: object) -> str:
    return hashlib.sha256(json_canonico(dados).encode("utf-8")).hexdigest()


def id_do_fato(source_url: str, tipo: str, afirmacao: str, valor: str = "") -> str:
    """Estável: a mesma afirmação, do mesmo tipo, na mesma fonte, tem o mesmo id
    em qualquer rodada ou run."""
    chave = "|".join(" ".join(str(x).lower().split()) for x in (source_url.rstrip("/"),
                                                                 tipo, valor, afirmacao))
    return "f_" + hashlib.sha256(chave.encode("utf-8")).hexdigest()[:12]
