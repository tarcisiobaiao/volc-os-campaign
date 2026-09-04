"""A ponte que faz o `Brief` nascer do Pautador e do Redator.

Hoje o `Brief` é um arquivo Python escrito à mão (`briefs/fgts_saque_aniversario.py`):
12 keywords digitadas, um destino colado, uma vertical declarada de memória. Este
módulo lê o que o ciclo já produziu — `pautador_keyword_clusters` (as keywords
triadas), `pautador_funnel_runs` (o funil escrito), `pautador_entities` (país,
idioma, vertical) e o `state.json` do motor (os fatos verificados) — e devolve
(1) um cockpit que a tela consegue explicar e (2) o `Brief` que o operador
escolheu montar.

## O que este módulo NÃO faz

Não fala com o Google Ads (nenhum CPC daqui é medido em conta), não escreve em
lugar nenhum, não gera copy e não decide por ninguém: `montar_brief` só converte
uma escolha já feita. E ele não inventa lance — ver `Escolha.cpc_inicial`.

## As três coisas que a medição na linha real mudou (opportunity_id=73, 18/08/2026)

**1 · Sub-intenção NÃO é ad group direto.** O `Brief` já aceita
`sub_intencoes` (um ad group por grupo) e é assim que este módulo o preenche —
mas a sub-intenção do funil não pode ir crua para lá.
`funis_sugeridos[].sub_intencoes` lista as keywords do TEMA;
`production_ads_queue` é a triagem do que serve a ANÚNCIO. Elas divergem, e
muito:

    sub-intenção     kw no funil   kw na fila de ads   volume declarado   volume real
    ACESSO                     7                   5             31.030        30.430
    ELEGIBILIDADE             26                  13             11.580         4.940
    VALOR                      5                   5              1.980         1.980
    OUTROS                     5                   0                530             0

Usar `volume_sub` como volume do ad group superestimaria ELEGIBILIDADE em 2,3×,
e OUTROS viraria um ad group sem uma única keyword. Por isso todo grupo aqui é a
INTERSEÇÃO, com o número declarado ao lado do recalculado — a divergência é
informação, não erro a ser escondido.

**2 · A triagem se contradiz em 5 keywords.** Elas estão em `production_ads_queue`
E em `content_seo_queue` ao mesmo tempo (medido: 5 de 23). Ficam no ad group,
marcadas com `tambem_em_conteudo` — quem escolhe é o operador.

**3 · O breakdown não é partição.** `summary.breakdown` soma 112, mas
`total_analyzed` é 100: uma keyword carrega de 1 a 3 tags. O denominador honesto
é `analisadas=100`. (A maquete do §4.2 do SPEC usa "de 112 mineradas" como se
fosse o total minerado — não é.)

## ⚠️ A PROCEDÊNCIA DO CPC — a razão de `Cpc` ser um objeto e não um float

`services_used` da linha é `["n8n:google_ads","n8n:dataforseo","n8n:gemini"]`, e
`avg_cpc_local` e `currency` são NULOS: nem a moeda está declarada. O
`DATAFORSEO-MEDIDO.md` mediu, com 96 chamadas e US$ 1,977 de fatura, que
`keyword_info.cpc` superestima o CPC real em 7,4× e **inverte a ordem dentro do
cluster** — nenhum fator de correção resolve.

Não afirmamos que estes CPCs vêm do DataForSEO: não temos o flow do n8n para
provar. Afirmamos o que é verdade — a procedência declarada é o que
`services_used` diz, e a moeda não está declarada. Por isso nenhum CPC sai daqui
como número pelado: todo CPC é um `Cpc` com `procedencia`, `moeda` e
`medido_na_conta`, e uma tela que renderizar só o `.valor` estará mentindo por
escolha própria, não por omissão desta camada.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .campanha.brief import Brief, Copy, SubIntencao
from .campanha.conteudo import SEVERIDADE_BARRA
from .campanha.criterio import Criterio, Evidencia, de_lista, deduplicar
from .policy import spec as _policy
from .referencia import geo as _geo

# ⚠️ A RÉGUA DE SEVERIDADE É UMA SÓ, E ELA MORA EM `campanha/conteudo.py`.
#
# `SEVERIDADE_BARRA` (`volc_ads/campanha/conteudo.py:56`) é `{"erro",
# "bloqueio", "limitacao"}`, e a nota de lá diz por que `limitacao` entra:
# FULLY_LIMITED deixou 57 anúncios sem veicular em 39 contas — anúncio que não
# veicula é reprovação com outro nome.
#
# Até 03/09/2026 este módulo tinha a SEGUNDA régua: `Cockpit.bloqueado` testava
# `== "bloqueio"` e nada mais, enquanto `policy/spec.json:776` já emitia
# `"severidade": "limitacao"`. Duas listas do mesmo veredito divergem na
# primeira mudança, e essa já tinha divergido.
#
# Importada, e não redigitada. `conteudo.py` não importa este módulo (ele só
# conhece `policy.spec`, `validacao` e `brief`), então não há ciclo — foi
# conferido antes de trocar a cópia pelo import.
#
# `erro` sobra no conjunto de propósito: nenhum `Aviso` do cockpit usa essa
# palavra hoje, mas um que passe a usar tem de barrar, e não escorregar por
# estar fora de uma lista curta demais.
SEVERIDADES_QUE_BARRAM = frozenset(SEVERIDADE_BARRA)

# Texto que a tela renderiza ao lado de todo CPC minerado. Fica aqui, e não na
# tela, porque é a mesma frase para os sete países e porque a versão curta que
# alguém escreveria no front ("CPC estimado") é exatamente o que o §2.2 do SPEC
# proíbe.
AVISO_CPC = (
    "CPC declarado pela mineração, NÃO medido na sua conta. O cluster não declara "
    "moeda (`currency` nulo). `services_used` inclui `n8n:dataforseo`, e o "
    "DATAFORSEO-MEDIDO.md mediu que `keyword_info.cpc` superestima o CPC real em "
    "7,4× e inverte a ordem dentro do cluster — não há fator de correção. Não "
    "temos o flow do n8n para provar de qual serviço veio este número."
)

# Vertical da entidade → vertical do `Brief`/`policy.spec`. MEDIDO em 18/08/2026
# sobre as 20 linhas de `pautador_entities`: financas 9, credito 6, seguros 2,
# gov_beneficios 1, educacao 1, saude 1 — os seis valores que existem hoje.
# Vertical desconhecida NÃO vira "informativo" em silêncio: gera aviso. Declarar
# "informativo" para uma página que intermedeia crédito é o defeito aberto do
# brief do FGTS, e ele custou o portão de habilitação inteiro.
VERTICAL_DA_ENTIDADE = {
    "credito": "financeiro",
    "financas": "financeiro",
    "seguros": "financeiro",
    "saude": "saude",
    "gov_beneficios": "governo_documentos",
    "educacao": "informativo",
}

_TAGS_HTML = re.compile(r"<[^>]+>")


class PonteIncompleta(ValueError):
    """O cockpit não tem o que o `Brief` exige. A mensagem diz o que falta."""


# ── procedência ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Cpc:
    """Um CPC que carrega de onde veio. Ver o ⚠️ do topo do módulo.

    ⚠️ `valor` é `float | None`, e `None` é AUSÊNCIA — nunca zero.

    Até 03/09/2026 `_cpc()` fazia `float(valor or 0.0)` e caía para `0.0` no
    `except`. Um CPC que a mineração não trouxe chegava à tela como "R$ 0,00",
    que não é silêncio: é a afirmação de que o clique é de graça. Um `0.0` que
    chegue aqui daqui em diante é um zero MEDIDO, e continua valendo como
    medição.
    """

    valor: float | None
    procedencia: str
    moeda: str | None = None
    medido_na_conta: bool = False


@dataclass(frozen=True)
class Aviso:
    """O que a tela precisa explicar.

    `severidade` tem QUATRO valores, e eles se separam em dois efeitos — não em
    quatro cores:

        bloqueio    BARRA. `montar_brief` levanta `PonteIncompleta` e não
                    existe parâmetro para suavizar.
        limitacao   BARRA, pela mesma porta. É o efeito FULLY_LIMITED do
                    `policy/spec.json`: o anúncio é aceito e não veicula, o que
                    é reprovação com outro nome (57 anúncios em 39 contas sob
                    GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES).
        atencao     INFORMA. O operador lê e decide; nada é impedido.
        informacao  INFORMA. Contexto do que a triagem já fez.

    ⚠️ A versão anterior deste docstring dizia que a severidade "é binária" e
    listava só três valores — e `Cockpit.bloqueado` testava só `== "bloqueio"`.
    `limitacao` já era emitida pelo spec e passava direto pelo portão. Quem
    decide o que barra é `SEVERIDADES_QUE_BARRAM`, no topo deste módulo, e ele
    é importado de `campanha/conteudo.py` para não haver duas listas.
    """

    codigo: str
    # bloqueio | limitacao (barram) · atencao | informacao (informam).
    # Ver `SEVERIDADES_QUE_BARRAM` — a régua é lá, não aqui.
    severidade: str
    titulo: str
    detalhe: str


# ── as peças do cockpit ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class KeywordCandidata:
    texto: str
    # `None` = a mineração não trouxe volume para este termo. Zero é uma
    # medição — "0 buscas/mês" é uma afirmação cara de se fazer por engano.
    volume: int | None
    cpc: Cpc
    competicao: str
    tendencia: int | None
    tags: tuple[str, ...]
    motivo: str
    # Está nas DUAS filas da triagem (anúncio e conteúdo). Medido: 5 de 23.
    tambem_em_conteudo: bool = False


@dataclass(frozen=True)
class GrupoCandidato:
    """Uma sub-intenção que sobrou depois da interseção com a fila de anúncio.

    É o candidato a AD GROUP. `volume`/`cpc_*` são recalculados sobre as
    keywords que de fato entram; `volume_declarado`/`keywords_declaradas` são o
    que a sub-intenção afirma. Os dois lados aparecem porque a diferença entre
    eles é o quanto da sub-intenção a triagem recusou.
    """

    tipo: str
    descricao: str
    keywords: tuple[KeywordCandidata, ...]
    # Soma dos volumes PRESENTES. `None` quando nenhuma keyword do grupo tem
    # volume: somar ausências e apresentar `0` diria que o grupo não tem busca,
    # que é o oposto de "não sei quanta busca ele tem".
    volume: int | None
    cpc_simples: Cpc
    cpc_ponderado: Cpc
    volume_declarado: int
    keywords_declaradas: int
    fora_da_fila: tuple[str, ...]

    @property
    def nome_ad_group(self) -> str:
        return self.tipo


@dataclass(frozen=True)
class Descartada:
    """O que a triagem tirou do anúncio. É informação, não lixo: explica o que
    a campanha deliberadamente NÃO compra."""

    texto: str
    volume: int | None
    cpc: Cpc
    motivo: str
    destino: str  # "conteudo"


@dataclass(frozen=True)
class Fato:
    """Fato verificado do funil, no formato que o `{fatos}` do `copy/PROMPT.md`
    especifica (id, tipo, texto, fonte).

    ⚠️ `copy/prompt.py` ainda monta o prompt sem estes fatos — o placeholder
    `{fatos}` do `PROMPT.md` não é preenchido por nenhum módulo hoje. Aqui eles
    existem porque o cockpit os mostra; quem os injetar será o Estágio 3.
    """

    id: str
    tipo: str  # afirmacao | numero
    texto: str
    fonte: str


@dataclass(frozen=True)
class Origem:
    """O que a campanha herda do funil de graça."""

    opportunity_id: int
    run_id: int | None
    project_id: int | None
    url_final: str
    url_procedencia: str
    status_wp: str
    post_type: str
    dominio: str
    nicho: str
    slug: str
    pais: str
    idioma: str
    idioma_declarado: str
    vertical: str
    vertical_declarada: str
    resumo_da_pesquisa: str
    fatos: tuple[Fato, ...]
    texto_da_lp: str


@dataclass(frozen=True)
class Triagem:
    """Os números da triagem que o Pautador já fez."""

    analisadas: int
    aprovadas_anuncio: int
    para_conteudo: int
    descartadas: int
    breakdown: dict[str, int]
    # ⚠️ OS DOIS SÃO `int | None`, E PELA MESMA RAZÃO DO `GrupoCandidato.volume`.
    #
    # `volume_total` é o `total_volume` DECLARADO na linha do cluster: quando a
    # coluna vem nula, a linha não declarou nada, e `0` seria uma declaração.
    # `volume_da_fila` é SOMA sobre `production_ads_queue`: soma os presentes e
    # só vira `None` quando NENHUM termo da fila tem volume. Uma soma parcial
    # continua sendo um número útil; uma soma de zero termos, não.
    volume_total: int | None
    volume_da_fila: int | None


@dataclass(frozen=True)
class Procedencia:
    servicos_declarados: tuple[str, ...]
    engine: str
    moeda_do_cluster: str | None
    moeda_da_oportunidade: str | None
    cpc_medio_do_cluster: float | None
    medido_na_conta: bool
    aviso: str


@dataclass(frozen=True)
class Cockpit:
    opportunity_id: int
    cluster_id: int | None
    origem: Origem | None
    triagem: Triagem | None
    grupos: tuple[GrupoCandidato, ...]
    descartadas: tuple[Descartada, ...]
    procedencia: Procedencia | None
    avisos: tuple[Aviso, ...]

    @property
    def bloqueado(self) -> bool:
        """O veredito de prontidão. É DAQUI que a tela e a rota o leem.

        ⚠️ Testava `== "bloqueio"` até 03/09/2026, e por isso um aviso de
        severidade `limitacao` — que `policy/spec.json:776` emite — passava
        pelo portão sem barrar nada.
        """
        return any(a.severidade in SEVERIDADES_QUE_BARRAM for a in self.avisos)

    @property
    def bloqueios(self) -> tuple[Aviso, ...]:
        return tuple(a for a in self.avisos if a.severidade in SEVERIDADES_QUE_BARRAM)

    def para_json(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        # As duas juntas, e não só a primeira: `bloqueado` diz QUE barrou e
        # `bloqueios` diz O QUE barrou. Emitir só o booleano obrigava quem
        # consome a refiltrar `avisos` por severidade — que é exatamente a
        # segunda régua que este módulo acabou de eliminar.
        d["bloqueado"] = self.bloqueado
        d["bloqueios"] = [dataclasses.asdict(a) for a in self.bloqueios]
        return d


# ── a escolha do operador, e o plano que sai dela ────────────────────────────
@dataclass(frozen=True)
class Escolha:
    """O que o operador marcou no cockpit. Tudo opcional tem default do `Brief`.

    `cpc_inicial` é `None` de propósito e NÃO é derivado do CPC minerado. Herdar
    o lance de um número que superestima 7,4× e inverte a ordem seria o erro que
    o `PORTOES_EXIGEM_MEDICAO` existe para impedir, só que com aparência de
    automação. Sem valor declarado, vale o default do `Brief` — e sai aviso.
    """

    grupos: tuple[str, ...] = ()  # tipos escolhidos; vazio = todos os candidatos
    keywords_fora: frozenset[str] = frozenset()  # desmarcadas, texto exato
    # ⚠️ A SELEÇÃO DO OPERADOR, KEYWORD A KEYWORD — e ela é AUTORIDADE.
    #
    # `{tipo: (texto, ...)}`. Quando um tipo aparece aqui, o ad group sai com
    # EXATAMENTE essas keywords, nessa ordem, e o grupo do cockpit deixa de ter
    # voz sobre o assunto.
    #
    # Existe porque o contrato anterior perdia a seleção em silêncio: o router
    # passava `{tipo: [keywords]}` para `grupos`, que é `tuple[str, ...]`, e
    # `set()` sobre um dict devolve as CHAVES. As keywords escolhidas nunca
    # chegavam aqui, e o builder montava o grupo inteiro. Medido contra a conta
    # real: duas escolhidas viraram oito no plano aprovado.
    #
    # `None` e `{}` significam "o operador não declarou seleção neste grupo" —
    # e isso NÃO é permissão para usar tudo. Quem quer o grupo inteiro diz o
    # nome disso em `grupos_usar_todas`.
    keywords_por_grupo: dict[str, tuple[str, ...]] | None = None
    # Onde o anúncio pode aparecer. `None` herda `REDE_LEGADA_SEARCH` (parceiros
    # ON) para não mudar campanha antiga em silêncio; o caminho novo declara.
    rede: Any = None
    # A declaração explícita de "use todas as keywords deste grupo". Ela existe
    # separada da ausência de propósito: ausência é dúvida, e dúvida não pode
    # resolver a favor da campanha mais larga.
    grupos_usar_todas: frozenset[str] = frozenset()
    budget_diario: float | None = None
    cpc_inicial: float | None = None
    # Maximize Conversions de Display pode carregar tCPA. Search ignora este
    # campo nesta onda; ausência preserva MaxConv puro.
    tcpa: float | None = None
    # Lance por sub-intenção, {tipo: cpc}. Mesma regra do `cpc_inicial`: só
    # entra CPC medido na conta. É o campo que a separação em ad groups existe
    # para servir — o spread medido entre as sub-intenções é de 9×.
    cpc_por_grupo: dict[str, float] = dataclasses.field(default_factory=dict)
    match_type: str | None = None
    negativas_campanha: tuple[str, ...] = ()
    negativas_adgroup: tuple[str, ...] = ()
    # O contrato TIPADO — o que o operador revisou keyword a keyword: match
    # type próprio, nível (campanha ou grupo), grupo, origem, motivo e
    # evidência. Preenchido, ele substitui `match_type`/`negativas_*` acima, e
    # o `Brief` recusa os dois ao mesmo tempo.
    #
    # É por aqui que `GrupoEscolhido.negativas` finalmente chega ao engine: a
    # negativa por sub-intenção existia no contrato HTTP desde sempre, mas
    # nenhum caminho a lia — `Escolha` não tinha onde guardá-la.
    criterios: tuple[Criterio, ...] = ()
    vertical: str | None = None  # sobrepõe a vertical herdada da entidade
    # O que a CONTA comprova ter. Vazio é o default seguro: `search.py` barra o
    # mutate quando a vertical exige certificação neste país e ela não está
    # declarada. Este módulo não lê `customer.*` — quem declara é o operador.
    certificacoes: tuple[str, ...] = ()
    url_final: str | None = None  # porta B do §4.1: destino colado à mão
    prefixo_nome: str | None = None
    # Congela os nomes entre a prova e a subida. Sem atravessar esta fronteira,
    # o `Brief` cai no relógio de `search.py` e duas montagens do mesmo pedido
    # produzem grafos diferentes.
    carimbo_nome: str | None = None
    conversao: str | None = None
    # Como a campanha nasce. `None` herda o default do `Brief` (MANUAL_CPC).
    # Ver docs/SPEC-FRONT-CAMPANHAS.md §1 para a doutrina e a razão de leilão.
    estrategia_lance: str | None = None
    # ⚠️ UM CONJUNTO. A sub-intenção continua sendo a lente da TRIAGEM — é como
    # o operador enxerga e marca as keywords — mas deixa de virar ad group.
    #
    # Doutrina fechada em 19/08/2026 (docs/SPEC-ARBITRAGEM.md P7): campanha =
    # rei, um termo, uma campanha, um conjunto. A razão é de mecânica: orçamento
    # é da CAMPANHA (`campaignBudgets`), lance é do ad group. Separar em N
    # grupos não separa verba — divide o aprendizado do RSA por N, e com
    # R$ 30/dia nenhum amadurece.
    conjunto_unico: bool = False


@dataclass(frozen=True)
class Plano:
    """O `Brief` pronto mais o que ele não consegue carregar.

    `Plano.grupos` é o mesmo recorte que virou `brief.sub_intencoes`, só que com
    volume, CPC, tags e motivo por keyword — o `Brief` carrega o nome e a lista
    de keywords, que é tudo de que `search.py` precisa. A tela usa `grupos`.
    """

    brief: Brief
    grupos: tuple[GrupoCandidato, ...]
    avisos: tuple[Aviso, ...]

    def para_json(self) -> dict[str, Any]:
        brief = dataclasses.asdict(self.brief)
        # `certificacoes` é um `set` no Brief e `json` não serializa set.
        brief["certificacoes"] = sorted(self.brief.certificacoes)
        return {
            "brief": brief,
            "geo_id": self.brief.geo_id,
            "idioma_id": self.brief.idioma_id,
            "nome_pais": self.brief.nome_pais,
            "grupos": [dataclasses.asdict(g) for g in self.grupos],
            "avisos": [dataclasses.asdict(a) for a in self.avisos],
        }


# ── as linhas cruas ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Linhas:
    """O que `montar_cockpit` consome. Separar a leitura da montagem é o que
    permite ao backend usar o `SupabaseService` dele (assíncrono, httpx) e a
    este módulo usar `urllib` na linha de comando, sem duas cópias da regra."""

    opportunity_id: int
    cluster: dict[str, Any] | None = None
    run: dict[str, Any] | None = None
    entidade: dict[str, Any] | None = None
    wordpress: dict[str, Any] | None = None
    estado_do_run: dict[str, Any] | None = None  # o `state.json` do motor
    run_dir: str | None = None


# ── normalização ─────────────────────────────────────────────────────────────
def _norm(texto: str) -> str:
    """Chave de comparação entre as duas filas e entre negativa e texto da LP.

    Casar por string crua funciona hoje (medido: as 23 keywords da fila batem
    exatamente com as das sub-intenções), mas um acento perdido numa reescrita do
    flow n8n faria a interseção esvaziar em silêncio — e ad group vazio é falha
    muda, a pior espécie.
    """
    t = unicodedata.normalize("NFD", (texto or "").strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t)


def _idioma_segmentavel(tag: str, pais: str) -> tuple[str, str]:
    """Traduz o idioma da entidade para um código que o Google Ads aceita.

    ⚠️ A entidade declara `pt-BR`, e `pt_BR` EXISTE no cache de idiomas com
    `segmentavel=False` (criterio 1016). Um `replace('-','_')` ingênuo produz
    `Brief(idioma="pt_BR")` e `geo.resolver` levanta ValueError. Medido em
    `referencia/dados/idiomas.json`: `pt` (1014) é segmentável, `pt_BR` não;
    o mesmo vale para `pt_PT`, `zh_CN` e companhia.

    Devolve (código, explicação) — a explicação vira aviso quando houve troca.
    """
    bruto = (tag or "").strip().replace("-", "_")
    todos = _geo.idiomas()
    if bruto and todos.get(bruto) and todos[bruto].segmentavel:
        return bruto, ""
    base = bruto.split("_")[0]
    if base and todos.get(base) and todos[base].segmentavel:
        return base, (
            f"idioma declarado {tag!r} não é segmentável no Google Ads; "
            f"usando {base!r}"
        )
    sugerido = _geo.sugerir_idioma(pais or "")
    if sugerido:
        return sugerido, (
            f"idioma declarado {tag!r} não resolve; usando a sugestão de "
            f"{pais}: {sugerido!r}"
        )
    raise PonteIncompleta(
        f"idioma {tag!r} não é segmentável e não há sugestão para o país "
        f"{pais!r}. Declare o idioma do anúncio na Escolha."
    )


# ── montagem do cockpit ──────────────────────────────────────────────────────
def _cpc(valor: Any, proc: str, moeda: str | None) -> Cpc:
    """Ausente entra, ausente sai. A procedência viaja em qualquer caso.

    ⚠️ As DUAS portas de ausência levavam a zero antes de 03/09/2026:
    `float(valor or 0.0)` transformava `None`/`""` em `0.0`, e o `except`
    devolvia `0.0` para lixo ilegível. As duas produziam a mesma frase na tela
    — "R$ 0,00" —, que afirma que o clique é de graça.

    O `Cpc` continua nascendo mesmo sem número: é ele que carrega a
    procedência, e "não medido, mineração X" é informação; um `None` pelado no
    lugar do objeto não seria.
    """
    if valor is None:
        return Cpc(valor=None, procedencia=proc, moeda=moeda, medido_na_conta=False)
    try:
        v: float | None = round(float(valor), 4)
    except (TypeError, ValueError):
        # Ilegível não é zero. Vira ausência, e a procedência diz de onde o
        # ilegível veio para alguém poder ir olhar.
        v = None
    return Cpc(valor=v, procedencia=proc, moeda=moeda, medido_na_conta=False)


def _procedencia(cluster: dict[str, Any] | None, entidade: dict[str, Any] | None) -> Procedencia:
    servicos = tuple((cluster or {}).get("services_used") or ())
    engine = str((cluster or {}).get("engine") or "desconhecido")
    return Procedencia(
        servicos_declarados=servicos,
        engine=engine,
        moeda_do_cluster=(cluster or {}).get("currency"),
        # A oportunidade declara BRL para os CPCs DELA (`cpc_min`/`cpc_max`), que
        # são outra medição. Aparece aqui como pista, nunca como a moeda do
        # cluster — dizer "é BRL" sem a linha declarar é inventar unidade.
        moeda_da_oportunidade=(entidade or {}).get("cpc_currency"),
        cpc_medio_do_cluster=(cluster or {}).get("avg_cpc_local"),
        medido_na_conta=False,
        aviso=AVISO_CPC,
    )


def _rotulo_procedencia(cluster: dict[str, Any] | None) -> str:
    c = cluster or {}
    servicos = ", ".join(c.get("services_used") or ()) or "não declarado"
    return (
        f"pautador_keyword_clusters#{c.get('id')} · engine {c.get('engine') or '?'} "
        f"· services_used: {servicos} · moeda não declarada"
    )


def _fila(entradas: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {_norm(e.get("keyword", "")): e for e in (entradas or []) if e.get("keyword")}


def _motivo(e: dict[str, Any]) -> str:
    """Por que a triagem mandou esta keyword para conteúdo.

    Medido: `reason` vem vazio em boa parte da `content_seo_queue` (as de
    `USER_QUESTION`, por exemplo). As tags são o motivo que sobrou — e "sem
    motivo declarado" é melhor que uma célula em branco na tela.
    """
    if e.get("reason"):
        return str(e["reason"])
    tags = ", ".join(e.get("tags") or ())
    return f"sem motivo declarado; tags: {tags}" if tags else "sem motivo declarado"


def _inteiro(v: Any) -> int | None:
    """Um inteiro, ou `None`. Nunca um zero de consolação."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _volume(e: dict[str, Any]) -> int | None:
    """O volume da entrada, com a ausência preservada.

    Era `int(e.get("volume") or 0)` em três lugares deste arquivo. Além de
    apagar a ausência, o `or` também apagava um `0` MEDIDO — os dois viravam a
    mesma coisa, e um deles é um fato sobre o termo.
    """
    return _inteiro(e.get("volume"))


def _candidata(e: dict[str, Any], proc: str, moeda: str | None, em_conteudo: bool) -> KeywordCandidata:
    return KeywordCandidata(
        texto=str(e.get("keyword") or ""),
        volume=_volume(e),
        cpc=_cpc(e.get("cpc"), proc, moeda),
        competicao=str(e.get("competition") or ""),
        tendencia=e.get("trend_score"),
        tags=tuple(e.get("tags") or ()),
        motivo=str(e.get("reason") or ""),
        tambem_em_conteudo=em_conteudo,
    )


def _rotulo_media(proc: str, tipo: str, presentes: int, total: int) -> str:
    """A procedência da média DIZ sobre quantas keywords ela foi feita.

    ⚠️ Uma média parcial apresentada como média do grupo é o defeito da
    ausência-como-zero com outra cara: em vez de inventar um número, inventa um
    denominador. Se 2 de 5 keywords têm CPC, o número é a média DAQUELAS DUAS —
    e quem lê a tela precisa saber disso sem abrir o grupo.
    """
    base = f"{proc} · {tipo}"
    if presentes == total:
        return base
    return f"{base} — PARCIAL: {presentes} de {total} keywords têm o dado"


def _agregar(
    kws: tuple[KeywordCandidata, ...], proc: str, moeda: str | None
) -> tuple[int | None, Cpc, Cpc]:
    """Volume somado e os DOIS CPCs do conjunto — sobre o que EXISTE.

    O simples é o que a sub-intenção declara em `metricas.cpc_medio`. O
    ponderado por volume é o que a régua de leilão do §5.3 precisa — em ACESSO
    os dois dão 0,72 e 0,88, e a diferença é uma keyword de 27.100 buscas
    puxando o conjunto.

    ⚠️ AS MÉDIAS SÃO DOS PRESENTES, E O DENOMINADOR TAMBÉM.

    Antes de 03/09/2026 a ausência de CPC já tinha virado `0.0` lá em `_cpc()`,
    e a média somava esses zeros com denominador cheio: cinco keywords das
    quais duas foram medidas produziam uma média DIVIDIDA POR CINCO — um número
    menor que qualquer CPC real do grupo, apresentado como o CPC do grupo.

    Agora ausência é `None`, e portanto:

      · a média sai sobre os valores presentes, com denominador igual à
        contagem dos presentes;
      · quando NENHUM está presente, a média é `None` — não `0.0`;
      · no ponderado, uma keyword sem volume não entra no PESO. Ela não tem
        como pesar, e dar-lhe peso zero silenciosamente é decidir que ela não
        importa em vez de admitir que não se sabe;
      · a procedência declara quando a média é parcial (ver `_rotulo_media`).
    """
    total = len(kws)

    volumes = [k.volume for k in kws if k.volume is not None]
    volume = sum(volumes) if volumes else None

    com_cpc = [k for k in kws if k.cpc is not None and k.cpc.valor is not None]
    simples = (
        round(sum(k.cpc.valor for k in com_cpc) / len(com_cpc), 4) if com_cpc else None
    )

    # Só entra no ponderado quem tem OS DOIS: o valor e o peso.
    com_peso = [k for k in com_cpc if k.volume is not None]
    peso = sum(k.volume for k in com_peso)
    ponderado = (
        round(sum(k.cpc.valor * k.volume for k in com_peso) / peso, 4)
        if peso else None
    )

    return (
        volume,
        _cpc(simples, _rotulo_media(proc, "média aritmética do grupo",
                                    len(com_cpc), total), moeda),
        _cpc(ponderado, _rotulo_media(proc, "média ponderada por volume",
                                      len(com_peso), total), moeda),
    )


def _grupos_do_funil(
    cluster: dict[str, Any], avisos: list[Aviso]
) -> tuple[tuple[GrupoCandidato, ...], tuple[Descartada, ...]]:
    proc = _rotulo_procedencia(cluster)
    moeda = cluster.get("currency")
    ads = _fila(cluster.get("production_ads_queue"))
    seo = _fila(cluster.get("content_seo_queue"))

    # O texto ORIGINAL, não a chave normalizada: a chave perde acento, e uma
    # tela que mostrasse "cartao de credito" faria o operador procurar no
    # Supabase uma string que não existe lá.
    ambas = sorted(ads[n].get("keyword", "") for n in set(ads) & set(seo))
    if ambas:
        avisos.append(Aviso(
            "KEYWORD_NAS_DUAS_FILAS", "informacao",
            f"{len(ambas)} keywords estão nas duas filas da triagem",
            "A mineração aprovou para anúncio e para conteúdo a mesma keyword. "
            "Elas entram no ad group marcadas com `tambem_em_conteudo` — quem "
            "decide é você: " + "; ".join(ambas[:5]),
        ))

    funis = sorted(
        cluster.get("funis_sugeridos") or [],
        key=lambda f: f.get("rank") if isinstance(f.get("rank"), int) else 99,
    )
    usadas: set[str] = set()
    grupos: list[GrupoCandidato] = []
    vazias: list[str] = []

    for sub in (funis[0].get("sub_intencoes") or []) if funis else []:
        tipo = str(sub.get("tipo") or "SEM_TIPO").upper()
        declaradas = [str(k.get("keyword") or "") for k in (sub.get("keywords") or [])]
        dentro = [n for n in (_norm(k) for k in declaradas) if n in ads]
        fora = [k for k in declaradas if _norm(k) not in ads]
        if not dentro:
            # ⚠️ Sub-intenção inteira fora da fila de anúncio (medido: OUTROS,
            # 5 de 5). Virar ad group aqui produziria um grupo com zero keyword,
            # que a API recusa — e um grupo que some sem explicação faz o
            # operador procurar o que nunca existiu.
            vazias.append(f"{tipo} ({len(declaradas)} kw, todas para conteúdo)")
            continue
        usadas.update(dentro)
        kws = tuple(
            _candidata(ads[n], proc, moeda, em_conteudo=n in seo) for n in dentro
        )
        volume, simples, ponderado = _agregar(kws, proc, moeda)
        grupos.append(GrupoCandidato(
            tipo=tipo,
            descricao=str(sub.get("descricao") or ""),
            keywords=kws,
            volume=volume,
            cpc_simples=simples,
            cpc_ponderado=ponderado,
            volume_declarado=int(sub.get("volume_sub") or 0),
            keywords_declaradas=len(declaradas),
            fora_da_fila=tuple(fora),
        ))

    if vazias:
        avisos.append(Aviso(
            "SUB_INTENCAO_SEM_ANUNCIO", "informacao",
            f"{len(vazias)} sub-intenção não virou ad group" if len(vazias) == 1
            else f"{len(vazias)} sub-intenções não viraram ad group",
            "Nenhuma keyword delas passou na triagem de anúncio: " + "; ".join(vazias),
        ))

    orfas = [n for n in ads if n not in usadas]
    if orfas:
        # Keyword aprovada para anúncio que nenhuma sub-intenção lista. Medido:
        # zero hoje. Cair num grupo próprio é melhor que sumir — a triagem
        # aprovou, e o dinheiro dela é tão real quanto o das outras.
        kws = tuple(_candidata(ads[n], proc, moeda, em_conteudo=n in seo) for n in orfas)
        volume, simples, ponderado = _agregar(kws, proc, moeda)
        grupos.append(GrupoCandidato(
            tipo="SEM_SUB_INTENCAO", descricao="Aprovadas para anúncio que "
            "nenhuma sub-intenção do funil rank 1 lista.",
            keywords=kws, volume=volume, cpc_simples=simples,
            cpc_ponderado=ponderado, volume_declarado=0,
            keywords_declaradas=len(orfas), fora_da_fila=(),
        ))
        avisos.append(Aviso(
            "KEYWORD_ORFA", "atencao",
            f"{len(orfas)} keywords de anúncio ficaram fora das sub-intenções",
            "Elas foram agrupadas em SEM_SUB_INTENCAO para não desaparecerem.",
        ))

    if not funis:
        avisos.append(Aviso(
            "SEM_SUB_INTENCOES", "atencao",
            "O cluster não traz funis sugeridos",
            "Sem sub-intenção não há divisão em ad groups: a fila de anúncio "
            "inteira virou um grupo único chamado SEM_SUB_INTENCAO.",
        ))

    descartadas = tuple(
        Descartada(
            texto=str(e.get("keyword") or ""),
            volume=_volume(e),
            cpc=_cpc(e.get("cpc"), proc, moeda),
            motivo=_motivo(e),
            destino="conteudo",
        )
        for n, e in seo.items() if n not in ads
    )
    return tuple(grupos), descartadas


def _texto_da_lp(estado: dict[str, Any] | None, pagina: int | None) -> str:
    """O texto da LP em uma string, para cruzar com as negativas.

    A LP não é prosa: `format` é `lp_json` e o conteúdo é um JSON de slots que o
    tema do WordPress monta. Achatar os valores e limpar as tags é suficiente
    para busca de substring, que é tudo o que a checagem de negativa precisa.
    """
    if not estado or pagina is None:
        return ""
    d = (estado.get("drafts") or {}).get(str(pagina)) or (estado.get("drafts") or {}).get(pagina) or {}
    bruto = d.get("content") or ""
    if not isinstance(bruto, str):
        return ""
    try:
        dados = json.loads(bruto)
        partes: list[str] = []

        def _achatar(v: Any) -> None:
            if isinstance(v, str):
                partes.append(v)
            elif isinstance(v, dict):
                for x in v.values():
                    _achatar(x)
            elif isinstance(v, list):
                for x in v:
                    _achatar(x)

        _achatar(dados)
        bruto = " ".join(partes)
    except (json.JSONDecodeError, TypeError):
        pass
    return _TAGS_HTML.sub(" ", bruto)


def _fatos(estado: dict[str, Any] | None, pagina: int | None) -> tuple[str, tuple[Fato, ...]]:
    """Normaliza a pesquisa do funil para o contrato `{fatos}` do `PROMPT.md`:
    cada fato com id, tipo, texto e fonte."""
    if not estado or pagina is None:
        return "", ()
    f = (estado.get("facts") or {}).get(str(pagina)) or (estado.get("facts") or {}).get(pagina) or {}
    saida: list[Fato] = []
    for i, d in enumerate(f.get("dados_validados") or [], 1):
        if d.get("fato"):
            saida.append(Fato(f"f{i}", "afirmacao", str(d["fato"]), str(d.get("fonte") or "")))
    for i, d in enumerate(f.get("fatos_verificados") or [], 1):
        texto = f"{d.get('valor','')}{d.get('unidade','')}".strip()
        if d.get("dispositivo"):
            texto = f"{texto} — {d['dispositivo']}"
        if d.get("vigente_desde"):
            texto = f"{texto} (vigente desde {d['vigente_desde']})"
        if texto:
            saida.append(Fato(f"n{i}", "numero", texto, str(d.get("fonte_primaria") or "")))
    return str(f.get("resumo") or ""), tuple(saida)


def _origem(linhas: Linhas, cluster: dict[str, Any] | None, avisos: list[Aviso]) -> Origem | None:
    run = linhas.run or {}
    ent = linhas.entidade or {}
    wp = linhas.wordpress or {}

    if not linhas.run:
        avisos.append(Aviso(
            "SEM_FUNIL", "bloqueio",
            "Esta oportunidade não tem funil escrito",
            "Sem `pautador_funnel_runs` não há LP para anunciar. Rode o Redator "
            "para este card, ou use a porta avulsa colando a URL à mão "
            "(Escolha.url_final) — e note que a herança e o cruzamento "
            "anúncio × página se perdem.",
        ))
        return None

    publicadas = run.get("paginas_publicadas") or []
    lp_post_type = wp.get("lp_post_type") or "r"
    # A LP é a página de destino; `/rec/` é navegação interna e NUNCA destino de
    # anúncio — inclusive de sitelink. A regra vem do brief do FGTS e é o que
    # impede a campanha de comprar clique para uma página de recirculação.
    lp = next(
        (p for p in publicadas
         if (p.get("role") or "").upper() == "LP" and p.get("post_type") == lp_post_type),
        None,
    )
    if lp is None:
        lp = next((p for p in publicadas if p.get("url_wp") and p.get("url_wp") == run.get("lp_url")), None)

    url = (lp or {}).get("url_wp") or run.get("lp_url") or ""
    if not url:
        avisos.append(Aviso(
            "SEM_LP", "bloqueio",
            "O funil não tem página publicada",
            f"`lp_url` está nulo e nenhuma das {len(publicadas)} páginas "
            "publicadas serve como destino. Publique a LP no WordPress ou cole "
            "a URL na Escolha.",
        ))
    if lp is not None and lp.get("post_type") and lp.get("post_type") != lp_post_type:
        avisos.append(Aviso(
            "DESTINO_NAO_E_LP", "bloqueio",
            f"O destino é um `{lp.get('post_type')}`, não a LP",
            "Páginas de recirculação são navegação interna e nunca destino de "
            f"anúncio. O post type de LP deste projeto é `{lp_post_type}`.",
        ))

    status_wp = str((lp or {}).get("status_wp") or "")
    if status_wp and status_wp != "publish":
        avisos.append(Aviso(
            "LP_EM_RASCUNHO", "atencao",
            f"A LP está como `{status_wp}` no WordPress",
            "Rascunho não é visível para quem não está logado: cada clique pago "
            "cairia num 404 ou numa tela de login. Publique antes de subir.",
        ))
    if url and ("?" in url or "p=" in url):
        avisos.append(Aviso(
            "URL_PROVISORIA", "atencao",
            "A URL de destino é provisória",
            f"{url} é a URL de rascunho do WordPress (query string). Quando a "
            "página for publicada o permalink muda, e o anúncio ficaria "
            "apontando para o endereço antigo.",
        ))

    pagina = (lp or {}).get("page_number")
    if linhas.estado_do_run is None:
        avisos.append(Aviso(
            "SEM_ARTEFATOS", "atencao",
            "Os arquivos deste run não estão no disco deste servidor",
            "Sem o `state.json` não há fatos verificados nem texto da LP: o "
            "cruzamento anúncio × página e o `{fatos}` da copy ficam sem lastro.",
        ))
    resumo, fatos = _fatos(linhas.estado_do_run, pagina)

    pais = str(ent.get("country_code") or "").upper()
    if not pais:
        avisos.append(Aviso(
            "SEM_PAIS", "bloqueio",
            "A entidade não declara país",
            "País e idioma são eixos independentes e ambos explícitos "
            "(`referencia/geo.py`). Sem país não há geo target.",
        ))
    idioma_declarado = str(ent.get("language") or "")
    idioma = idioma_declarado
    if pais:
        try:
            idioma, nota = _idioma_segmentavel(idioma_declarado, pais)
            if nota:
                avisos.append(Aviso("IDIOMA_TROCADO", "informacao", "Idioma ajustado", nota))
        except PonteIncompleta as e:
            avisos.append(Aviso("SEM_IDIOMA", "bloqueio", "Idioma não resolvido", str(e)))

    vertical_declarada = str(ent.get("vertical") or "")
    vertical = VERTICAL_DA_ENTIDADE.get(vertical_declarada, "")
    if not vertical:
        vertical = "informativo"
        avisos.append(Aviso(
            "VERTICAL_DESCONHECIDA", "atencao",
            f"Vertical {vertical_declarada or '(vazia)'} não está no mapa",
            "Assumi `informativo`, que é a vertical SEM portão de habilitação. "
            f"Confira: as verticais conhecidas são {sorted(VERTICAL_DA_ENTIDADE)}.",
        ))
    _avisar_habilitacao(vertical, pais, avisos)

    return Origem(
        opportunity_id=linhas.opportunity_id,
        run_id=run.get("id"),
        project_id=run.get("project_id"),
        url_final=url,
        url_procedencia=(
            f"pautador_funnel_runs#{run.get('id')} · página {pagina} · "
            f"post_type {(lp or {}).get('post_type') or '?'}"
        ),
        status_wp=status_wp,
        post_type=str((lp or {}).get("post_type") or ""),
        dominio=str(wp.get("wp_url") or ""),
        nicho=str(ent.get("canonical_name") or (cluster or {}).get("main_keyword") or ""),
        slug=str((lp or {}).get("slug") or ent.get("slug") or ""),
        pais=pais,
        idioma=idioma,
        idioma_declarado=idioma_declarado,
        vertical=vertical,
        vertical_declarada=vertical_declarada,
        resumo_da_pesquisa=resumo,
        fatos=fatos,
        texto_da_lp=_texto_da_lp(linhas.estado_do_run, pagina),
    )


def _avisar_habilitacao(vertical: str, pais: str, avisos: list[Aviso]) -> None:
    """O portão país × vertical do `policy/spec.json`, dito antes de gastar.

    Não é sobre texto: é elegibilidade, e reprova a campanha inteira. Para a
    linha real (vertical `credito` → `financeiro`, país BR) o spec exige
    verificação de serviços financeiros — é a decisão aberta do `COMECE-AQUI.md`
    chegando à tela em vez de ficar num comentário.

    ⚠️ Sai como `atencao` mesmo quando o Google classifica como `bloqueio`, e a
    diferença é de fato: `bloqueio` aqui significa "não dá para montar o Brief",
    e a habilitação NÃO é isso — ela depende de a conta já estar verificada, o
    que se lê em `customer.*` no Google Ads e este módulo não fala com a API.
    Reprovar por dado não lido seria inventar medição; a severidade declarada
    pelo Google vai no texto, inteira, para o operador decidir.
    """
    try:
        hab = _policy.carregar()["habilitacao"].get(vertical)
    except (OSError, KeyError, json.JSONDecodeError):
        return
    if not hab or pais not in (hab.get("paises_exigem") or []):
        return
    avisos.append(Aviso(
        "HABILITACAO_EXIGIDA", "atencao",
        f"A vertical `{vertical}` exige {hab['exige']} em {pais}",
        f"{hab.get('nota') or ''} Severidade declarada pelo Google: "
        f"{hab.get('severidade')}. Sem isso o anúncio é reprovado "
        f"independentemente do texto. Fonte: {hab.get('url')}",
    ))


def montar_cockpit(linhas: Linhas) -> Cockpit:
    """O objeto que a tela usa para montar o cockpit — puro, sem rede.

    Nenhum caminho devolve lista vazia muda: todo estado degradado sai com um
    `Aviso` que diz o que houve e o que fazer.
    """
    avisos: list[Aviso] = []
    cluster = linhas.cluster

    if cluster is None:
        avisos.append(Aviso(
            "SEM_CLUSTER", "bloqueio",
            "Esta oportunidade não tem cluster de keywords",
            "`pautador_keyword_clusters` não tem linha para este "
            f"`opportunity_id` ({linhas.opportunity_id}). Rode a mineração de "
            "keywords do Pautador antes de montar a campanha.",
        ))
        # Segue montando a origem mesmo assim: um card sem cluster mas com funil
        # publicado precisa dizer as duas coisas na mesma tela.
        origem = _origem(linhas, None, avisos)
        return Cockpit(linhas.opportunity_id, None, origem, None, (), (), None, tuple(avisos))

    ads = cluster.get("production_ads_queue") or []
    seo = cluster.get("content_seo_queue") or []
    if not ads:
        avisos.append(Aviso(
            "SEM_FILA_DE_ANUNCIO", "bloqueio",
            "A triagem não aprovou nenhuma keyword para anúncio",
            f"O cluster #{cluster.get('id')} tem {len(seo)} keywords em "
            "`content_seo_queue` e nenhuma em `production_ads_queue`. Este tema "
            "serve a conteúdo, não a compra de clique — as descartadas estão "
            "listadas para você conferir a triagem.",
        ))

    grupos, descartadas = _grupos_do_funil(cluster, avisos)
    origem = _origem(linhas, cluster, avisos)

    resumo = cluster.get("summary") or {}
    breakdown = resumo.get("breakdown") or {}
    # A SOMA É SOBRE OS PRESENTES, E A AUSÊNCIA TOTAL NÃO VIRA ZERO.
    #
    # Somar `0` por termo sem volume dava um total menor que o real e
    # indistinguível de um total honesto. Agora a soma inclui só quem declarou;
    # `None` aparece apenas quando NENHUM termo da fila declarou volume, que é
    # o único caso em que não há número nenhum para somar.
    volumes_da_fila = [v for v in (_volume(e) for e in ads) if v is not None]
    volume_da_fila = sum(volumes_da_fila) if volumes_da_fila else None
    # `total_volume` é DECLARAÇÃO da linha, não soma nossa: coluna nula é linha
    # que não declarou, e `0` seria uma declaração de que não há busca.
    volume_total = _inteiro(cluster.get("total_volume"))
    # `is not None` e não truthiness: com o `if volume_total and ...` antigo,
    # uma linha que declarasse `0` contra uma fila de 30.430 não gerava aviso
    # nenhum — a divergência mais gritante era a única silenciosa.
    if (volume_total is not None and volume_da_fila is not None
            and volume_total != volume_da_fila):
        avisos.append(Aviso(
            "VOLUME_DIVERGE", "informacao",
            "`total_volume` não é a soma da fila de anúncio",
            f"A linha declara {volume_total} e a fila soma {volume_da_fila}. O "
            "número que vale para a campanha é o da fila.",
        ))
    declaradas = resumo.get("ads_approved")
    if isinstance(declaradas, int) and declaradas != len(ads):
        avisos.append(Aviso(
            "TRIAGEM_DIVERGE", "atencao",
            "`summary.ads_approved` não bate com a fila",
            f"O resumo diz {declaradas} e `production_ads_queue` tem "
            f"{len(ads)}. Vale a fila — é dela que saem as keywords.",
        ))

    triagem = Triagem(
        # `total_analyzed` é o denominador honesto: somar o breakdown dá 112
        # porque uma keyword carrega de 1 a 3 tags.
        analisadas=int(resumo.get("total_analyzed") or 0),
        aprovadas_anuncio=len(ads),
        para_conteudo=len(seo),
        descartadas=int(breakdown.get("discards") or 0),
        breakdown={k: int(v) for k, v in breakdown.items() if isinstance(v, int)},
        volume_total=volume_total,
        volume_da_fila=volume_da_fila,
    )

    return Cockpit(
        opportunity_id=linhas.opportunity_id,
        cluster_id=cluster.get("id"),
        origem=origem,
        triagem=triagem,
        grupos=grupos,
        descartadas=descartadas,
        procedencia=_procedencia(cluster, linhas.entidade),
        avisos=tuple(avisos),
    )


# ── a escolha vira Brief ─────────────────────────────────────────────────────
def montar_brief(cockpit: Cockpit, escolha: Escolha | None = None,
                 *, copy: Copy | None = None) -> Plano:
    """Converte a escolha do operador num `Brief` válido.

    Levanta `PonteIncompleta` quando o cockpit tem bloqueio ou quando a escolha
    esvazia as keywords. Não existe parâmetro para forçar: portão é decisão
    binária, e a escotilha que "só suaviza um pouquinho" é exatamente o que fez
    o classificador de pauta absolver 52 casos seguidos.
    """
    escolha = escolha or Escolha()
    avisos: list[Aviso] = []

    # A porta B do §4.1 (URL colada à mão) SATISFAZ o requisito de destino — não
    # o afrouxa. Por isso ela desarma SEM_LP/SEM_FUNIL, e só esses.
    manual = (escolha.url_final or "").strip()
    bloqueios = [a for a in cockpit.bloqueios
                 if not (manual and a.codigo in ("SEM_LP", "SEM_FUNIL"))]
    if bloqueios:
        raise PonteIncompleta(
            "o cockpit tem bloqueio: "
            + " | ".join(f"{a.codigo}: {a.titulo} — {a.detalhe}" for a in bloqueios)
        )
    if manual:
        avisos.append(Aviso(
            "URL_MANUAL", "atencao",
            "Destino colado à mão",
            "A campanha perde a herança do funil e o cruzamento anúncio × "
            "página: ninguém confere se o texto do anúncio corresponde ao que a "
            "página entrega.",
        ))

    origem = cockpit.origem
    if origem is None and not manual:
        raise PonteIncompleta(
            "sem origem e sem URL manual: não há destino para a campanha."
        )

    tipos = set(escolha.grupos) if escolha.grupos else {g.tipo for g in cockpit.grupos}
    desconhecidos = tipos - {g.tipo for g in cockpit.grupos}
    if desconhecidos:
        raise PonteIncompleta(
            f"grupos inexistentes no cockpit: {sorted(desconhecidos)}. "
            f"Disponíveis: {sorted(g.tipo for g in cockpit.grupos)}"
        )

    fora = {_norm(k) for k in escolha.keywords_fora}
    selecao = dict(escolha.keywords_por_grupo or {})
    usar_todas = set(escolha.grupos_usar_todas or ())

    # Contradição declarada é recusa, não precedência. Escolher a seleção
    # silenciaria o "use todas"; escolher o grupo inteiro silenciaria a seleção.
    # As duas resoluções descartam uma ordem que alguém deu de propósito.
    ambos = {t for t in usar_todas if selecao.get(t)}
    if ambos:
        raise PonteIncompleta(
            f"os grupos {sorted(ambos)} declaram seleção de keywords E "
            "`usar todas` ao mesmo tempo. As duas coisas são ordens diferentes; "
            "escolher uma delas por conta própria descartaria a outra."
        )
    desconhecidos_sel = set(selecao) - {g.tipo for g in cockpit.grupos}
    if desconhecidos_sel:
        raise PonteIncompleta(
            f"seleção de keywords para grupos inexistentes: {sorted(desconhecidos_sel)}."
        )

    grupos: list[GrupoCandidato] = []
    keywords: list[str] = []
    for g in cockpit.grupos:
        if g.tipo not in tipos:
            continue
        if g.tipo in selecao and g.tipo not in usar_todas:
            # ⚠️ AQUI A SELEÇÃO MANDA, E O GRUPO NÃO TEM VOTO.
            #
            # Nada de interseção "por segurança": interseção com o grupo inteiro
            # é justamente o caminho pelo qual uma seleção vira sugestão. O que
            # o operador não escolheu não entra, e o que ele escolheu e não
            # existe derruba o plano em vez de sumir.
            pedidas = tuple(selecao[g.tipo])
            if not pedidas:
                raise PonteIncompleta(
                    f"o grupo {g.tipo} veio com seleção de keywords VAZIA. "
                    "Ausência não é permissão para usar o grupo inteiro: se a "
                    "intenção é essa, declare o tipo em `grupos_usar_todas`."
                )
            por_norma = {_norm(k.texto): k for k in g.keywords}
            vistos: set[str] = set()
            escolhidas: list[Any] = []
            for texto in pedidas:
                n = _norm(texto)
                if not n:
                    raise PonteIncompleta(
                        f"o grupo {g.tipo} recebeu uma keyword vazia na seleção."
                    )
                if n not in por_norma:
                    raise PonteIncompleta(
                        f"a keyword {texto!r} não pertence ao grupo {g.tipo}. "
                        "Uma seleção que aponta para fora do grupo não é um "
                        "pedido válido, e aceitá-la calado faria o operador "
                        f"achar que subiu. Disponíveis: "
                        f"{sorted(k.texto for k in g.keywords)}"
                    )
                if n in vistos:      # dedup preserva a PRIMEIRA ocorrência
                    continue         # e nunca amplia o conjunto
                vistos.add(n)
                escolhidas.append(por_norma[n])
            # A ordem é a do pedido, não a do cockpit: a mesma entrada precisa
            # produzir sempre a mesma chave de idempotência.
            kws = tuple(k for k in escolhidas if _norm(k.texto) not in fora)
        else:
            kws = tuple(k for k in g.keywords if _norm(k.texto) not in fora)
        if not kws:
            avisos.append(Aviso(
                "GRUPO_ESVAZIADO", "atencao",
                f"O grupo {g.tipo} ficou sem keyword",
                "Todas foram desmarcadas; ele não vira ad group.",
            ))
            continue
        # A procedência sai da própria keyword: ela já a carrega desde a
        # montagem do cockpit, e reconstruí-la aqui abriria espaço para as duas
        # divergirem depois de um refactor.
        volume, simples, ponderado = _agregar(kws, kws[0].cpc.procedencia, kws[0].cpc.moeda)
        grupos.append(dataclasses.replace(
            g, keywords=kws, volume=volume,
            cpc_simples=simples, cpc_ponderado=ponderado,
        ))
        keywords.extend(k.texto for k in kws)

    if not keywords:
        raise PonteIncompleta(
            "nenhuma keyword sobrou depois da escolha. Marque ao menos um grupo "
            "e deixe ao menos uma keyword dentro dele."
        )

    if escolha.cpc_inicial is None:
        avisos.append(Aviso(
            "CPC_NAO_DECLARADO", "atencao",
            "Lance inicial não declarado",
            "O CPC minerado NÃO foi usado como lance — ele superestima o CPC "
            "real em 7,4× e inverte a ordem dentro do cluster. Vale o default "
            "do Brief. Declare `cpc_inicial` a partir de medição na conta "
            "(GAQL em `keyword_view`) antes de subir.",
        ))
    if copy is None or not (copy.headlines or copy.descriptions):
        avisos.append(Aviso(
            "COPY_VAZIA", "atencao",
            "O Brief está sem copy",
            "O Estágio 3 (geração + cascata) ainda não rodou. `search.py` "
            "montaria um RSA sem headline e a API recusaria o mutate.",
        ))

    # Todas as negativas declaradas, venham do contrato antigo ou do tipado.
    # Ler só `negativas_campanha` faria o aviso abaixo parar de disparar no dia
    # em que o cockpit passasse a mandar `criterios` — o defeito continuaria
    # existindo e o aviso que o denuncia é que teria sumido.
    negativas = tuple(escolha.negativas_campanha) or tuple(
        c.texto for c in escolha.criterios if c.negativa
    )
    if origem is not None and origem.texto_da_lp and negativas:
        alvo = _norm(origem.texto_da_lp)
        colidem = [n for n in negativas if _norm(n) and _norm(n) in alvo]
        if colidem:
            # O defeito medido no brief do FGTS: ele negativa `meutudo`,
            # `nubank`, `bmg` e `santander` — as quatro marcas que a própria LP
            # usa como argumento. Barato de checar, caro de descobrir depois.
            avisos.append(Aviso(
                "NEGATIVA_NO_TEXTO_DA_LP", "atencao",
                f"{len(colidem)} negativas aparecem no texto da LP",
                "A campanha bloqueia termos que a página usa como argumento: "
                + ", ".join(colidem),
            ))

    url = manual or (origem.url_final if origem else "")
    if not url.startswith("https://"):
        raise PonteIncompleta(
            f"destino {url!r} não é https. `Brief.__post_init__` recusa, e sem "
            "https o anúncio não sobe."
        )

    pais = (origem.pais if origem else "") or "BR"
    idioma = (origem.idioma if origem else "") or _geo.sugerir_idioma(pais) or "pt"
    campos: dict[str, Any] = {
        "nicho": (origem.nicho if origem else "") or "sem nicho declarado",
        "slug": (origem.slug if origem else "") or "",
        "url_final": url,
        "copy": copy or Copy(),
        "pais": pais,
        "idioma": idioma,
        "vertical": escolha.vertical or (origem.vertical if origem else "informativo"),
        "certificacoes": set(escolha.certificacoes),
        **_negativas_do_brief(escolha, negativas, _um_conjunto_so(grupos, escolha)),
        **_keywords_do_brief(grupos, escolha),
    }
    for nome, valor in (
        ("budget_diario", escolha.budget_diario),
        ("cpc_inicial", escolha.cpc_inicial),
        ("tcpa", escolha.tcpa),
        ("match_type", escolha.match_type),
        ("prefixo_nome", escolha.prefixo_nome),
        ("carimbo_nome", escolha.carimbo_nome),
        ("conversao", escolha.conversao),
        ("estrategia_lance", escolha.estrategia_lance),
        # A rede declarada atravessa. `None` continua herdando o legado
        # nomeado dentro de `comum.py`, e não um literal solto.
        ("rede", escolha.rede),
    ):
        if valor is not None:
            campos[nome] = valor

    brief = Brief(**campos)  # valida país × idioma, https, budget e match type

    sem_lance = [s.nome for s in brief.sub_intencoes if s.cpc_inicial is None]
    if len(brief.sub_intencoes) > 1 and sem_lance:
        avisos.append(Aviso(
            "GRUPO_SEM_LANCE_PROPRIO", "informacao",
            f"{len(sem_lance)} de {len(brief.sub_intencoes)} ad groups herdam o "
            "lance da campanha",
            "O spread de CPC entre sub-intenções é o motivo de elas serem ad "
            "groups separados. Sem lance próprio, o grupo caro e o barato "
            "compram ao mesmo preço: " + ", ".join(sem_lance),
        ))

    return Plano(brief=brief, grupos=tuple(grupos), avisos=tuple(avisos))


def _um_conjunto_so(grupos: list[GrupoCandidato], escolha: Escolha) -> bool:
    """A topologia colapsa para UM ad group?

    Uma função só, porque a condição é lida em dois lugares — as keywords e os
    critérios — e dois predicados “quase iguais” é como a negativa acaba
    apontando para um grupo que as keywords já não têm.
    """
    return bool(escolha.conjunto_unico) or (
        len(grupos) == 1 and grupos[0].tipo == "SEM_SUB_INTENCAO"
    )


def _negativas_do_brief(
    escolha: Escolha, negativas: tuple[str, ...], achatar: bool
) -> dict[str, Any]:
    """As negativas no formato que o `Brief` aceita — tipadas OU `list[str]`.

    Os dois contratos são exclusivos, e o `Brief` recusa os dois preenchidos.
    Aqui a precedência é declarada: quem manda `criterios` mandou o contrato
    novo, e as listas antigas ficam vazias — nunca as duas coisas, porque com
    as duas uma delas sumiria do payload sem aviso.
    """
    if escolha.criterios:
        crits = escolha.criterios
        if achatar:
            crits = tuple(_achatar_criterios(crits))
        return {
            "criterios": list(crits),
            "negativas_campanha": [],
            "negativas_adgroup": [],
        }
    return {
        "negativas_campanha": list(negativas),
        "negativas_adgroup": list(escolha.negativas_adgroup),
    }


def _achatar_criterios(criterios: tuple[Criterio, ...]) -> list[Criterio]:
    """Tira o rótulo de grupo de todo critério de ad group.

    Serve ao caminho `conjunto_unico`, em que as N sub-intenções viram UM ad
    group: um critério que continuasse apontando para `"ACESSO"` apontaria para
    um grupo que não existe mais, e `Brief` o recusaria.

    ⚠️ Isto NÃO promove negativa de grupo para negativa de campanha — o nível
    continua `AD_GROUP`. Com um ad group só, "vale neste grupo" e "vale em
    todos os grupos" são a mesma coisa; o dia em que `conjunto_unico` for
    desligado, a negativa volta a precisar do rótulo, e é por isso que o
    achatamento acontece aqui, na ponte que decidiu a topologia, e não lá
    dentro do construtor.
    """
    return [
        dataclasses.replace(c, grupo=None) if c.nivel == "AD_GROUP" else c
        for c in criterios
    ]


def _keywords_do_brief(grupos: list[GrupoCandidato], escolha: Escolha) -> dict[str, Any]:
    """As keywords no formato que o `Brief` aceita — `keywords` OU `sub_intencoes`.

    O `Brief` recusa os dois preenchidos, e por um bom motivo: keyword que
    ficasse só na lista chapada não entraria em ad group nenhum e sumiria sem
    o payload denunciar. Aqui a regra é: um ad group por sub-intenção, sempre —
    exceto quando o único grupo é o sintético `SEM_SUB_INTENCAO`, que existe
    justamente porque não havia sub-intenção. Nesse caso a lista chapada faz
    `Brief.grupos()` devolver o grupo-sentinela e `search.py` mantém o nome
    histórico `AdGroup_{carimbo}`.
    """
    # ⚠️ A lista chapada é o caminho da DOUTRINA agora, não mais só o do grupo
    # sentinela. Com `conjunto_unico`, todas as keywords marcadas entram num ad
    # group só — `Brief.grupos()` devolve o grupo-sentinela e `search.py` mantém
    # o nome histórico `AdGroup_{carimbo}`. Ver `Escolha.conjunto_unico`.
    if _um_conjunto_so(grupos, escolha):
        return {"keywords": [k.texto for g in grupos for k in g.keywords],
                "sub_intencoes": []}
    return {
        "keywords": [],
        "sub_intencoes": [
            SubIntencao(
                nome=g.tipo,
                keywords=[k.texto for k in g.keywords],
                # Só CPC MEDIDO na conta entra aqui. O minerado fica fora por
                # decisão declarada — ver `Escolha.cpc_inicial`.
                cpc_inicial=escolha.cpc_por_grupo.get(g.tipo),
            )
            for g in grupos
        ],
    }


# ── leitura (a porta de linha de comando) ────────────────────────────────────
class _LeitorPostgrest:
    """GET no PostgREST com `urllib`. Só leitura — não há método de escrita.

    O backend NÃO usa isto: ele tem o `SupabaseService` dele (assíncrono, httpx)
    e monta `Linhas` com as próprias consultas. Isto existe para que
    `python -m volc_ads.pautador_ponte 73` funcione sem arrastar `pydantic` e
    sem depender do `cwd` — o `Settings` do backend lê `.env` relativo ao
    diretório atual, e da raiz do repositório ele não encontra `SUPABASE_URL`.
    """

    def __init__(self, base: str, chave: str, timeout: float = 30.0):
        self.base = base.rstrip("/")
        self.chave = chave
        self.timeout = timeout

    def select(self, tabela: str, params: dict[str, str]) -> list[dict[str, Any]]:
        url = f"{self.base}/rest/v1/{tabela}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url, headers={"apikey": self.chave, "Authorization": f"Bearer {self.chave}"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read() or b"[]")


def _env_do_disco(raiz: Path) -> dict[str, str]:
    """Lê SUPABASE_URL/SERVICE_ROLE de `backend/.env` ou `.env.server`.

    Os dois arquivos existem e divergem: a raiz tem `VITE_SUPABASE_URL` (que o
    backend não lê) e `.env.server` tem `SUPABASE_URL`. Procurar nos dois evita
    o "credencial não encontrada" que na verdade é "olhei no arquivo errado".
    """
    out = {k: v for k, v in os.environ.items()
           if k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")}
    for nome in ("backend/.env", ".env.server", ".env"):
        if out.get("SUPABASE_URL") and out.get("SUPABASE_SERVICE_ROLE_KEY"):
            break
        arq = raiz / nome
        if not arq.exists():
            continue
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            if k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY") and not out.get(k):
                out[k] = v.strip()
    return out


def _run_dir(carimbo: str, raiz: Path) -> Path | None:
    """A pasta do run do motor. Mesma regra do `redator/worker._achar_run_dir`:
    o carimbo é o único identificador estável (o slug o `dedupe_slugs` muda)."""
    runs = raiz / "funnelforge-migracao" / "engine" / "runs"
    if not runs.is_dir():
        return None
    candidatas = [d for d in runs.iterdir() if d.is_dir() and d.name.endswith(carimbo)]
    definitivas = [d for d in candidatas if not d.name.startswith("_pending")]
    return (definitivas or candidatas or [None])[0]


def carregar(opportunity_id: int, *, run_id: int | None = None,
             leitor: Any = None, raiz: Path | None = None) -> Linhas:
    """Busca as linhas no Supabase e o `state.json` no disco. Só leitura."""
    raiz = raiz or Path(__file__).resolve().parents[1]
    if leitor is None:
        env = _env_do_disco(raiz)
        if not env.get("SUPABASE_URL") or not env.get("SUPABASE_SERVICE_ROLE_KEY"):
            raise PonteIncompleta(
                "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY não encontrados no "
                f"ambiente nem em {raiz}/backend/.env, {raiz}/.env.server."
            )
        leitor = _LeitorPostgrest(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])

    def um(tabela: str, params: dict[str, str]) -> dict[str, Any] | None:
        linhas = leitor.select(tabela, {**params, "limit": "1"})
        return linhas[0] if linhas else None

    cluster = um("pautador_keyword_clusters",
                 {"opportunity_id": f"eq.{opportunity_id}", "order": "created_at.desc"})
    filtro = {"id": f"eq.{run_id}"} if run_id else {
        "opportunity_id": f"eq.{opportunity_id}", "order": "criado_em.desc"}
    run = um("pautador_funnel_runs", filtro)
    # O card do pautador é `pautador_entity_opportunities` (entity-first) e é lá
    # que estão país e `cpc_currency`; `pautador_entities` tem idioma e vertical.
    # Medido: `pautador_opportunities` NÃO tem a linha 73.
    oportunidade = um("pautador_entity_opportunities", {"id": f"eq.{opportunity_id}"})
    entidade = None
    if oportunidade and oportunidade.get("entity_id"):
        entidade = um("pautador_entities", {"id": f"eq.{oportunidade['entity_id']}"})
    if entidade is not None:
        entidade = {**entidade, "cpc_currency": (oportunidade or {}).get("cpc_currency")}

    wordpress = None
    if run and run.get("project_id"):
        wordpress = um("project_wordpress", {"project_id": f"eq.{run['project_id']}"})

    estado, pasta = None, None
    carimbo = ((run or {}).get("artefatos") or {}).get("carimbo")
    if carimbo:
        pasta = _run_dir(str(carimbo), raiz)
        if pasta is not None:
            try:
                estado = json.loads((pasta / "state.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                estado = None

    return Linhas(
        opportunity_id=opportunity_id, cluster=cluster, run=run, entidade=entidade,
        wordpress=wordpress, estado_do_run=estado,
        run_dir=str(pasta) if pasta else None,
    )


def cockpit(opportunity_id: int, **kw: Any) -> Cockpit:
    """Atalho: lê e monta. O backend deve preferir `montar_cockpit(Linhas(...))`
    com as consultas dele — esta função é síncrona e bloquearia o event loop."""
    return montar_cockpit(carregar(opportunity_id, **kw))


def _ausente(v: Any, formato: str = "") -> str:
    """`None` vira um travessão, não um zero — nem no terminal.

    O CLI é a ferramenta que se abre justamente quando o cluster está estranho;
    um `0` impresso ali mandaria o operador procurar um problema de volume que
    não existe, quando o que existe é dado que não veio.
    """
    if v is None:
        return "—"
    return format(v, formato) if formato else str(v)


def _imprimir(c: Cockpit) -> None:
    o = c.origem
    print(f"opportunity {c.opportunity_id} · cluster {c.cluster_id}")
    if o:
        print(f"  destino   {o.url_final}  [{o.status_wp or 'sem status'}]")
        print(f"  herança   nicho={o.nicho!r} slug={o.slug!r} "
              f"{o.pais}/{o.idioma} (declarado {o.idioma_declarado}) "
              f"vertical={o.vertical} (declarada {o.vertical_declarada})")
        print(f"  fatos     {len(o.fatos)} · LP com {len(o.texto_da_lp)} chars de texto")
    if c.triagem:
        t = c.triagem
        print(f"  triagem   {t.aprovadas_anuncio} para anúncio · {t.para_conteudo} "
              f"para conteúdo · {t.descartadas} descartes · de {t.analisadas} analisadas")
        print(f"            volume da fila {_ausente(t.volume_da_fila)} "
              f"(linha declara {_ausente(t.volume_total)})")
    print(f"\n  {'grupo':<16} {'kw':>7} {'volume':>9} {'declarado':>10} "
          f"{'CPC simples':>12} {'CPC pond.':>10}")
    for g in c.grupos:
        # `_ausente` porque volume e CPC agora podem ser `None`: um `:.2f`
        # sobre `None` levanta, e o CLI é a ferramenta que se usa justamente
        # quando o cluster está estranho.
        print(f"  {g.tipo:<16} {len(g.keywords):>3}/{g.keywords_declaradas:<3} "
              f"{_ausente(g.volume):>9} {g.volume_declarado:>10} "
              f"{_ausente(g.cpc_simples.valor, '.2f'):>12} "
              f"{_ausente(g.cpc_ponderado.valor, '.2f'):>10}")
    if c.procedencia:
        p = c.procedencia
        print(f"\n  procedência: services_used={list(p.servicos_declarados)} · "
              f"engine={p.engine} · moeda do cluster={p.moeda_do_cluster!r} · "
              f"moeda da oportunidade={p.moeda_da_oportunidade!r} · "
              f"medido na conta={p.medido_na_conta}")
    print(f"\n  descartadas para conteúdo: {len(c.descartadas)}")
    for d in c.descartadas[:3]:
        print(f"    {d.texto!r} vol {_ausente(d.volume)} · {d.motivo}")
    print(f"\n  avisos ({len(c.avisos)}):")
    for a in c.avisos:
        print(f"    [{a.severidade:<11}] {a.codigo}: {a.titulo}")
        print(f"                  {a.detalhe}")


if __name__ == "__main__":  # pragma: no cover
    import sys

    opp = int(sys.argv[1]) if len(sys.argv) > 1 else 73
    c = cockpit(opp)
    _imprimir(c)
    if not c.bloqueado:
        plano = montar_brief(c, Escolha(cpc_inicial=0.20, budget_diario=10.0))
        b = plano.brief
        print(f"\n  BRIEF: {sum(len(g.keywords) for g in b.grupos())} keywords em "
              f"{len(b.grupos())} ad groups {[g.nome for g in b.grupos()]} · "
              f"geo {b.geo_id} · idioma {b.idioma_id} · vertical {b.vertical}")
        for a in plano.avisos:
            print(f"    [{a.severidade:<11}] {a.codigo}: {a.titulo}")
