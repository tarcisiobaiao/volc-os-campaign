"""O inventário operacional — o que existe nas contas, e quão recente é isso.

Este módulo é o **núcleo comum** do Hub de Tráfego (ADR-17). Ele descreve uma
campanha sem saber que canal ela é: nenhuma das entidades filhas que o gate
mecânico da §9.4 do SPEC manda procurar aparece aqui — e este texto não as
nomeia justamente porque o gate é um `rg` pelos nomes delas, e um comentário
que as cita transformaria a prova num falso positivo. O que um canal injeta
entra por `PerfilDeCanal`, declarado em `sincronizador.py` e implementado em
`adaptador_search.py`.

## As três regras que atravessam o arquivo inteiro

1. **Nenhum número sem frescor.** `Entrega.__post_init__` LEVANTA se houver um
   número sem `leitura`. Não é validação defensiva: é a única forma de garantir
   que um custo não chegue à tela sem a data em que foi lido — e alguém decide
   gasto olhando para ele.

2. **Ausência é `None`, nunca zero.** Falha ao medir produz `None`. Zero é um
   fato: a campanha não apareceu. A tela renderiza os dois de formas diferentes
   ("—" e "0"), e converter um no outro inventa um resultado que ninguém mediu.

3. **Falha de uma conta não contamina as outras.** O envelope fica `parcial`,
   `faltou` diz o que não deu para ler, e o último snapshot bom da conta que
   falhou **continua visível** — com o carimbo da última leitura BOA, que é mais
   antiga que a última tentativa.

## ⚠️ ESTE CAMINHO NÃO PODE TOCAR NO GOOGLE ADS

A leitura sai do snapshot em Postgres, sempre. Medido em 24/08/2026,
`/api/trafego/alertas` roda ~5 GAQL por conta em tempo de render, e o sino e o
Layout chamam essa rota — ou seja, abrir qualquer página do produto custa rede
para o Google. `tests/test_trafego_inventario.py::test_leitura_nao_toca_no_google_ads`
falha se este módulo, ou o router que o serve, importar `volc_ads` ou
`google.ads`. O import é o gate; não há como "só desta vez".

## Por que cursor opaco, e nunca offset

A lista muda entre páginas: uma sincronização entra no meio da paginação e
`offset=50` passa a apontar para outro item — o operador pula uma campanha ou vê
a mesma duas vezes, sem nada na tela dizendo isso. O cursor daqui é keyset sobre
`(customer_id, volc_campaign_id)`, que é único e estável, e carrega a assinatura
dos filtros: reusar um cursor com outro filtro é recusado em vez de devolver
lixo silencioso.
"""
from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple

from app.trafego import dominio as dom

log = logging.getLogger("volc.trafego.inventario")

# ── contrato ────────────────────────────────────────────────────────────────

#: Versão do contrato de leitura comum. Sobe quando um consumidor precisa ser
#: avisado. ⚠️ Canal novo é ADIÇÃO, não mudança de versão (SPEC §10.3): se um
#: canal fizer este número subir, o núcleo vazou.
#:
#: **v2 (U0, 26/08/2026).** Três mudanças que um cliente v1 não sobrevive em
#: silêncio, e por isso o número sobe:
#:
#:   1. o padrão passa a excluir histórico removido — um cliente v1 que
#:      contasse a resposta acharia que 79 campanhas sumiram do banco;
#:   2. `totais` troca de forma: `campanhas` sai, entram `operacionais`,
#:      `historicas` e `geral`. Manter `campanhas` como apelido de um dos três
#:      seria dois nomes para coisas diferentes conforme o recorte;
#:   3. o cursor passa a carregar o degrau de ordenação. Um cursor v1 colado
#:      aqui pularia ou repetiria linhas, e a resposta pareceria correta —
#:      por isso ele é RECUSADO com mensagem, e não reinterpretado.
VERSAO_INVENTARIO = 2

# ── vocabulário fechado ─────────────────────────────────────────────────────
#
# ⚠️ NADA AQUI É DEFINIDO NESTE ARQUIVO. Cada nome abaixo é um APELIDO do que
# `dominio.py` declara, e a diferença importa: até esta rodada as duas listas
# eram cópias independentes, e cópias divergem. Três divergências foram medidas
# antes de sumirem — a regra de conjunto, a ordem entre `velho` e
# `vazio_confirmado`, e `MANUAL_CPM` no teto de cliques.
#
# Manter os apelidos (em vez de fazer o resto do arquivo escrever
# `dom.RECENTE`) é o que deixa a mudança pequena e revisável: o que sai daqui é
# a REGRA, não o endereço.

REMOVIDA = "removida"
NAO_ENCONTRADA = "nao_encontrada"
CONTA_NAO_IDENTIFICADA = "conta_nao_identificada"
FORA_DE_ESCOPO = "fora_de_escopo"
SINCRONIZACAO_FALHOU = "sincronizacao_falhou"
LEGADO_NAO_RECONCILIADO = "legado_nao_reconciliado"

#: O sétimo estado, que é da API e não do banco — ver `dominio.PRESENTE`.
PRESENTE = dom.PRESENTE

#: Os sete que a resposta pode emitir. A ordem é estável porque
#: `GET /inventario/vocabulario` a serve para a tela.
ESTADOS_DE_PRESENCA: Tuple[str, ...] = (
    PRESENTE,
    REMOVIDA,
    NAO_ENCONTRADA,
    CONTA_NAO_IDENTIFICADA,
    FORA_DE_ESCOPO,
    SINCRONIZACAO_FALHOU,
    LEGADO_NAO_RECONCILIADO,
)

RECENTE = dom.RECENTE
VELHO = dom.VELHO
PARCIAL = dom.PARCIAL
FALHOU = dom.FALHOU
NUNCA_LIDO = dom.NUNCA_LIDO
VAZIO_CONFIRMADO = dom.VAZIO_CONFIRMADO

FRESCORES: Tuple[str, ...] = dom.FRESCORES

VOLC_OS = "volc_os"
DESCOBERTA = "descoberta"
LEGADO = "legado"
DESCONHECIDA = "desconhecida"

PROCEDENCIAS: Tuple[str, ...] = (VOLC_OS, DESCOBERTA, LEGADO, DESCONHECIDA)

#: Vocabulário canônico de canal (ADR-18): os nomes do enum do Google Ads.
#: `PERFORMANCE_MAX` é o nome de contrato; `PMAX` é apelido de tela e só é
#: aceito na ENTRADA de filtro — nunca sai daqui.
SEARCH = "SEARCH"
DISPLAY = "DISPLAY"
DEMAND_GEN = "DEMAND_GEN"
PERFORMANCE_MAX = "PERFORMANCE_MAX"
VIDEO = "VIDEO"
SHOPPING = "SHOPPING"

CANAIS: Tuple[str, ...] = dom.CANAIS_DO_CONTRATO
APELIDOS_DE_CANAL = dom.APELIDOS_DE_LEITURA

MANUAL_CPC = "MANUAL_CPC"
MAXIMIZE_CONVERSIONS = "MAXIMIZE_CONVERSIONS"
ESTRATEGIAS: Tuple[str, ...] = (MANUAL_CPC, MAXIMIZE_CONVERSIONS)

#: A conta das linhas que não têm conta. NÃO é um id do Google: não é numérico,
#: então `escopo.exigir_escopo()` o recusa antes de qualquer requisição sair
#: daqui. É o que permite agrupar `legado_nao_reconciliado` sem inventar um
#: `customer_id` que alguém poderia reenviar como se fosse real.
SEM_CONTA = "conta-nao-identificada"

#: A partir de quantos segundos uma leitura passa a aparecer como `velho`.
#: A política mora em `dominio.JANELA_RECENTE_S`; aqui é o nome que a rota
#: `/inventario/vocabulario` publica para a tela.
SEGUNDOS_PARA_VELHO = dom.JANELA_RECENTE_S

#: Teto de linhas por página. Sem teto, um cliente pede `limite=100000` e a
#: resposta volta com o corte do PostgREST (1000) SEM DIZER que cortou — que é
#: o defeito que `SupabaseService.select_all` existe para contornar.
LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200


class CursorInvalido(ValueError):
    """Cursor malformado, de outra versão, ou de outro conjunto de filtros."""


class SemFrescor(ValueError):
    """Tentativa de emitir um número sem a data em que ele foi lido."""


# ── as formas do contrato ───────────────────────────────────────────────────
#
# Espelham `src/types/trafego.ts`, nome por nome. `dataclasses.asdict` é a
# serialização: aqui as dataclasses SÃO a forma do fio, ao contrário de
# `projecao.py`, onde `asdict` vazaria o artigo inteiro da landing page.


@dataclass(frozen=True)
class Leitura:
    """Um instante medido, sempre acompanhado do que ele descreve."""

    lido_em: str
    idade_s: int


@dataclass(frozen=True)
class Entrega:
    """Uma medida de entrega. `None` é "não deu para medir"; 0 é zero medido."""

    impressoes: Optional[int] = None
    cliques: Optional[int] = None
    custo_micros: Optional[int] = None
    moeda: Optional[str] = None
    leitura: Optional[Leitura] = None

    def __post_init__(self) -> None:
        tem_numero = any(v is not None for v in
                         (self.impressoes, self.cliques, self.custo_micros))
        if tem_numero and self.leitura is None:
            raise SemFrescor(
                "entrega com número e sem leitura: um custo sem data é "
                "indistinguível de um custo de ontem, e alguém decide gasto "
                "olhando para ele"
            )


@dataclass(frozen=True)
class IdentidadeExterna:
    customer_id: str
    campaign_id: str

    def __post_init__(self) -> None:
        if not str(self.customer_id or "").strip():
            raise ValueError(
                "identidade externa sem customer_id. Linha sem conta usa o "
                f"sentinela {SEM_CONTA!r}, que não é um id do Google e é "
                "recusado pelo portão de escopo se alguém o reenviar."
            )


@dataclass(frozen=True)
class VinculoDeFunil:
    opportunity_id: Optional[int]
    project_id: Optional[int]
    confirmado_por: Optional[str]
    confirmado_em: Optional[str]


@dataclass(frozen=True)
class CampanhaNoInventario:
    volc_campaign_id: str
    campaign_lineage_id: Optional[str]
    externa: IdentidadeExterna
    nome: str
    estado_externo: Optional[str]
    veiculacao: Optional[str]
    canal: Optional[str]
    estrategia: Optional[str]
    lance_micros: Optional[int]
    verba_diaria_micros: Optional[int]
    teto_de_cliques: Optional[int]
    entrega: Entrega
    vinculo: Optional[VinculoDeFunil]
    procedencia: str
    presenca: str
    cockpit_href: Optional[str]


@dataclass(frozen=True)
class ContaNoInventario:
    customer_id: str
    nome: Optional[str]
    frescor: str
    leitura: Optional[Leitura]
    ultima_leitura_boa: Optional[Leitura]
    motivo: Optional[str]
    quantidade: int
    campanhas: List[CampanhaNoInventario]


@dataclass(frozen=True)
class Faltou:
    customer_id: Optional[str]
    escopo: str
    motivo: str


@dataclass(frozen=True)
class Inventario:
    versao: int
    frescor: str
    leitura: Optional[Leitura]
    parcial: bool
    faltou: List[Faltou]
    contas: List[ContaNoInventario]
    proximo_cursor: Optional[str]
    totais: Dict[str, int]

    def json(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


# ── filtros ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FiltrosDoInventario:
    """Filtros combináveis. Tudo vazio = não filtra.

    Tuplas e não listas porque a assinatura do cursor precisa de um valor
    imutável e ordenável: um filtro que muda depois de o cursor ser emitido
    faria a página seguinte descrever outro conjunto.
    """

    #: Texto livre — casa com nome OU id externo. Resolvido no banco.
    busca: str = ""
    #: O histórico removido entra na listagem?
    #:
    #: **O padrão é `False`**, e essa é a mudança de comportamento da U0. Medido
    #: em 26/08/2026: das 84 campanhas, 79 estão `REMOVED`. Abrir o Hub em
    #: história é abrir em 94% de ruído, com as 5 campanhas que existem de fato
    #: empurradas para fora da primeira página.
    #:
    #: O histórico não some do banco nem da API: ele é pedido. E ele é pedido
    #: também quando o operador filtra explicitamente por um estado histórico —
    #: ver `normalizar_filtros`.
    #:
    #: ⚠️ Entra na `assinatura()` de propósito. Se ficasse fora, um cursor
    #: emitido sobre o recorte operacional serviria a página 2 do histórico, e
    #: nada na resposta denunciaria.
    incluir_historico: bool = False
    conta: Tuple[str, ...] = ()
    projeto: Tuple[int, ...] = ()
    canal: Tuple[str, ...] = ()
    estado_externo: Tuple[str, ...] = ()
    presenca: Tuple[str, ...] = ()
    frescor: Tuple[str, ...] = ()
    procedencia: Tuple[str, ...] = ()
    atencao: Optional[bool] = None
    vinculado: Optional[bool] = None

    def assinatura(self) -> str:
        """Impressão digital estável do conjunto. Entra no cursor.

        Sem ela, colar o cursor da página 2 numa consulta com outro filtro
        devolveria uma página coerente e ERRADA — o pior tipo de defeito de
        paginação, porque nada na resposta denuncia.
        """
        cru = json.dumps(dataclasses.asdict(self), sort_keys=True, default=list)
        return hashlib.sha256(cru.encode("utf-8")).hexdigest()[:16]


def normalizar_filtros(cru: Dict[str, Any]) -> FiltrosDoInventario:
    """Traduz o que veio da query string para o vocabulário canônico.

    Canal passa pelos apelidos (`PMAX` → `PERFORMANCE_MAX`, ADR-18); valor fora
    do vocabulário é recusado com a lista do que existe, em vez de virar um
    filtro que não casa com nada e parece "não tem campanha".
    """
    def _lista(chave: str) -> Tuple[str, ...]:
        v = cru.get(chave) or ()
        if isinstance(v, str):
            v = [p for p in v.split(",") if p.strip()]
        return tuple(str(x).strip() for x in v if str(x).strip())

    canais: List[str] = []
    for c in _lista("canal"):
        alvo = APELIDOS_DE_CANAL.get(c.upper(), c.upper())
        if alvo not in CANAIS:
            raise ValueError(
                f"canal {c!r} não existe no vocabulário. Os canais são: "
                f"{', '.join(CANAIS)}."
            )
        canais.append(alvo)

    for nome, valores, permitido in (
        ("presenca", _lista("presenca"), ESTADOS_DE_PRESENCA),
        ("frescor", _lista("frescor"), FRESCORES),
        ("procedencia", _lista("procedencia"), PROCEDENCIAS),
    ):
        for v in valores:
            if v not in permitido:
                raise ValueError(
                    f"{nome} {v!r} não existe. Os valores são: "
                    f"{', '.join(permitido)}."
                )

    projetos: List[int] = []
    for p in _lista("projeto"):
        try:
            projetos.append(int(p))
        except ValueError as exc:
            raise ValueError(f"projeto {p!r} não é um número.") from exc

    # A busca é higienizada aqui, na fronteira, e não na tradução para query
    # param: `,` `(` `)` `*` e `.` são a GRAMÁTICA do PostgREST, e um deles no
    # meio do texto não vira "nenhum resultado" — vira outra consulta. Trocar
    # por espaço mantém a intenção do operador e tira a arma.
    bruto = str(cru.get("busca") or "").strip()
    for simbolo in (",", "(", ")", "*", "."):
        bruto = bruto.replace(simbolo, " ")
    busca = " ".join(bruto.split())[:80]

    # ── o filtro explícito manda no padrão ──────────────────────────────────
    #
    # Pedir `estado_externo=REMOVED` e receber lista vazia seria mentira: o
    # operador nomeou exatamente aquilo que o padrão esconde. Então um filtro
    # explícito de estado ou de presença DECLARA o universo, e o padrão sai de
    # cena — sem precisar que a tela mande dois parâmetros combinados.
    #
    # A regra é uma frase: *o padrão só decide quando o operador não decidiu*.
    # `incluir_historico=true` continua funcionando sozinho, para quem quer o
    # operacional E a história na mesma lista.
    estados = tuple(v.upper() for v in _lista("estado_externo"))
    presencas = _lista("presenca")
    pediu_historico_por_estado = (
        dom.REMOVED in estados or dom.REMOVIDA in presencas
    )

    return FiltrosDoInventario(
        busca=busca,
        incluir_historico=bool(cru.get("incluir_historico")) or pediu_historico_por_estado,
        conta=_lista("conta"),
        projeto=tuple(projetos),
        canal=tuple(canais),
        estado_externo=estados,
        presenca=presencas,
        frescor=_lista("frescor"),
        procedencia=_lista("procedencia"),
        atencao=cru.get("atencao"),
        vinculado=cru.get("vinculado"),
    )


# ── cursor ──────────────────────────────────────────────────────────────────


#: A forma de um `customer_id`: só dígitos.
#:
#: ⚠️ Deliberadamente mais FROUXA que o CHECK do banco (`{6,12}`). O que esta
#: expressão precisa garantir é que o texto não carregue gramática do PostgREST
#: — vírgula, parêntese, ponto. Exigir o comprimento aqui não acrescenta
#: segurança nenhuma e cria um modo de falha próprio: uma conta fora do formato
#: esperado deixaria de PAGINAR, e o operador veria a listagem terminar cedo sem
#: erro. Validar identidade é trabalho do CHECK; aqui é só a forma do texto.
_CONTA_VALIDA = re.compile(r"^[0-9]{1,20}$")

#: A forma de um `volc_campaign_id`. Espelha o CHECK
#: `trafego_campanha_volc_id_valido` da v9_01 — o mesmo alfabeto, o mesmo teto.
_CHAVE_VALIDA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


def gerar_cursor(customer_id: str, ordem: int, volc_campaign_id: str,
                 filtros: FiltrosDoInventario) -> str:
    """Keyset opaco. Nunca offset — ver o cabeçalho do módulo.

    ⚠️ **Três chaves, e a ordem delas é a ordem do `ORDER BY`.** Um keyset só
    funciona quando carrega TODAS as colunas de ordenação: a página seguinte é
    "o que vem depois desta tupla", e uma tupla incompleta descreve um ponto que
    não existe na ordenação real.

    Com a ordem `(customer_id, ordem_operacional, volc_campaign_id)` e um cursor
    de duas chaves, o predicado `volc_campaign_id > k` dentro da mesma conta
    saltaria todo o degrau seguinte — a página 2 começaria depois do último id
    do degrau 0, e as campanhas ligadas do degrau 1 com id menor sumiriam da
    listagem inteira. Nenhuma mensagem, nenhum buraco visível: só campanhas que
    o operador nunca vê.
    """
    carga = {
        "v": VERSAO_INVENTARIO,
        "f": filtros.assinatura(),
        "c": str(customer_id),
        "o": int(ordem),
        "k": str(volc_campaign_id),
    }
    cru = json.dumps(carga, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(cru).decode("ascii").rstrip("=")


def ler_cursor(cursor: str,
               filtros: FiltrosDoInventario) -> Tuple[str, int, str]:
    """Devolve `(customer_id, ordem_operacional, volc_campaign_id)`, ou levanta.

    Recusa em quatro casos, e cada um tem mensagem própria: base64 quebrado,
    versão diferente do contrato, filtro diferente do que gerou o cursor, e
    degrau de ordenação ausente ou ilegível.
    """
    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        carga = json.loads(base64.urlsafe_b64decode(preenchido.encode("ascii")))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise CursorInvalido("cursor malformado.") from exc

    if not isinstance(carga, dict):
        raise CursorInvalido("cursor malformado.")
    if carga.get("v") != VERSAO_INVENTARIO:
        raise CursorInvalido(
            f"cursor de outra versão do contrato (v{carga.get('v')}); "
            f"esta API fala v{VERSAO_INVENTARIO}. Recomece a listagem."
        )
    if carga.get("f") != filtros.assinatura():
        raise CursorInvalido(
            "cursor de outro conjunto de filtros. Continuar daqui pularia ou "
            "repetiria campanhas sem nada na tela dizendo isso. Recomece a "
            "listagem com os filtros novos."
        )
    # ── forma das chaves, antes de elas virarem gramática ──────────────────
    #
    # ⚠️ `c` e `k` são interpolados dentro da expressão booleana do PostgREST
    # (`or(customer_id.gt.<c>,and(...))`). O cursor é opaco, não assinado: quem
    # colar um base64 forjado escolhe o TEXTO que entra nessa árvore.
    #
    # Um `k` contendo `)),or(...` reescreve a árvore inteira — anula o keyset ou
    # devolve 400. Não é vazamento entre contas (o `or` das famílias continua
    # cercando o conjunto), mas é uma consulta que o operador não pediu, e a
    # resposta parece legítima.
    #
    # As duas chaves têm forma conhecida e fechada, e conferi-la aqui é mais
    # barato e mais seguro que escapar na tradução: o que não tem a forma não
    # vira consulta nenhuma.
    conta = str(carga.get("c") or "")
    chave = str(carga.get("k") or "")
    if not (conta == SEM_CONTA or _CONTA_VALIDA.match(conta)):
        raise CursorInvalido(
            "cursor com conta em formato inesperado. Recomece a listagem.")
    if not _CHAVE_VALIDA.match(chave):
        raise CursorInvalido(
            "cursor com identificador em formato inesperado. Recomece a "
            "listagem.")

    # O degrau é `int` e precisa existir. Recuar para zero seria pior que
    # recusar: a página seguinte começaria do topo do degrau de atenção e
    # repetiria tudo o que o operador já viu, com cara de resultado novo.
    bruto = carga.get("o")
    if not isinstance(bruto, int) or isinstance(bruto, bool):
        raise CursorInvalido(
            "cursor sem o degrau de ordenação. Ele é uma das três chaves do "
            "keyset; sem ele a página seguinte descreveria um ponto que não "
            "existe na ordenação. Recomece a listagem."
        )

    return conta, bruto, chave


# ── frescor ─────────────────────────────────────────────────────────────────


def _para_dt(valor: Any) -> Optional[datetime]:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        d = valor
    else:
        texto = str(valor).strip().replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(texto)
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def leitura_de(quando: Any, agora: Optional[datetime] = None) -> Optional[Leitura]:
    """Um `Leitura` a partir de um carimbo. `None` quando não houve leitura.

    A idade viaja calculada porque o cliente que a calculasse usaria o relógio
    DELE — e um navegador com relógio adiantado mostraria "lido há -3 min".
    """
    d = _para_dt(quando)
    if d is None:
        return None
    ref = agora or datetime.now(timezone.utc)
    idade = int((ref - d).total_seconds())
    return Leitura(lido_em=d.astimezone(timezone.utc).isoformat(),
                   idade_s=max(idade, 0))


def frescor_da_conta(linha: Dict[str, Any],
                     agora: Optional[datetime] = None) -> str:
    """O frescor de UMA conta, a partir da linha de `trafego_snapshot_conta`.

    ⚠️ Esta função NÃO decide nada — ela adapta. A regra é
    `dominio.frescor_da_conta`, e o que mora aqui é só a tradução da linha do
    banco (com os apelidos de coluna) para os argumentos dela.

    Havia uma segunda implementação neste lugar, com ordem própria de perguntas.
    A diferença ficou medida em dois pontos: uma leitura `parcial` do
    sincronizador e uma leitura vazia e antiga saíam com frescores diferentes
    conforme quem projetava. Duas réguas para a mesma medida não é redundância,
    é o sistema discordando de si mesmo.
    """
    c = normalizar_linha_de_conta(linha)
    tentativa = _para_dt(c.get("lido_em"))
    ultima_boa = _para_dt(c.get("ultima_leitura_boa_em"))

    resultado = str(c.get("resultado") or "").strip() or None
    if resultado is None and tentativa is None and ultima_boa is None:
        return NUNCA_LIDO

    # ⚠️ O CARIMBO É O DA ÚLTIMA LEITURA BOA, nunca o da última tentativa.
    # Regra C dentro da conta: quando a tentativa de agora falhou, o dado na
    # tela é o de antes, e a idade que a tela mostra tem de ser a DELE. Usar
    # `tentativa_em` faria um snapshot de ontem aparecer com dois minutos.
    if ultima_boa is None and resultado not in (None, FALHOU):
        # `ok` sem nenhuma leitura boa registrada: o snapshot está incompleto e
        # não há data para sustentar número nenhum.
        return NUNCA_LIDO

    try:
        return dom.frescor_da_conta(
            resultado=resultado,
            lido_em=ultima_boa,
            campanhas=_inteiro(c.get("lidas")),
            motivo=c.get("motivo"),
            agora=agora or datetime.now(timezone.utc),
            janela_recente_s=SEGUNDOS_PARA_VELHO,
        )
    except dom.LeituraAusente:
        # A regra levanta quando alguém diz "ok" sem carimbo. Na LEITURA isso
        # não pode derrubar a página: a conta entra como nunca lida, que é a
        # afirmação mais fraca e verdadeira disponível.
        log.warning("snapshot da conta %s diz 'ok' sem carimbo de leitura boa",
                    c.get("customer_id"))
        return NUNCA_LIDO


# ── regras de projeção — todas delegadas ao domínio ─────────────────────────
#
# As quatro funções abaixo eram implementações próprias. Cada uma tinha uma
# gêmea em `dominio.py`, e ao menos uma discordava dela. O que sobrou é o
# endereço: o nome continua aqui porque o resto do arquivo (e os testes) o
# usam, e a regra mora num lugar só.

def teto_de_cliques(verba_micros: Optional[int], lance_micros: Optional[int],
                    estrategia: Optional[str]) -> Optional[int]:
    """Verba ÷ lance, quando o número tem unidade de clique. Regra no domínio."""
    return dom.teto_de_cliques(
        verba_diaria_micros=verba_micros,
        lance_micros=lance_micros,
        estrategia=estrategia,
    )


def canal_canonico(bruto: Any) -> Optional[str]:
    """O canal que a resposta emite. Fora do contrato vira `None`."""
    return dom.canal_de_leitura(bruto)


def estrategia_canonica(bruto: Any) -> Optional[str]:
    return dom.estrategia_de_leitura(bruto)


def presenca_efetiva(armazenada: Any, conta_falhou: bool) -> str:
    """A presença que a tela mostra. Regra em `dominio.presenca_projetada`."""
    return dom.presenca_projetada(armazenada, conta_falhou=conta_falhou)


def pede_atencao(linha: Dict[str, Any], *, conta_falhou: bool) -> bool:
    """A condição de atenção de UMA linha do espelho.

    ⚠️ Ela é DERIVADA, e não lida de uma coluna. A tabela antiga tinha um
    booleano gerado chamado `atencao`; `v9_01_trafego_inventario.sql` não tem —
    e não ter é melhor, porque a regra passa a ser a mesma para o sino, para a
    aba e para o quadro de alertas, em vez de três leituras de uma coluna que
    só o banco sabia calcular.

    O preço está declarado em `FonteDeInventario.campanhas`: quem implementa a
    porta precisa saber traduzir esta condição para o banco, porque filtrar aqui
    faria a paginação cortar ANTES do filtro.
    """
    return dom.pede_atencao(
        presenca_armazenada=linha.get("presenca"),
        estado_externo=linha.get("estado_externo"),
        impressoes=_inteiro(linha.get("impressoes")),
        cliques=_inteiro(linha.get("cliques")),
        entrega_medida=_para_dt(linha.get("entrega_lida_em")) is not None,
        conta_falhou=conta_falhou,
    )


#: As colunas de `trafego_snapshot_conta` traduzidas para o vocabulário interno
#: deste módulo. UMA direção, um schema.
#:
#: Havia aqui uma PONTE entre dois conjuntos de nomes — `lido_em`/`tentativa_em`,
#: `resultado`/`tentativa_resultado`, e assim por diante — porque duas frentes
#: escreveram schemas diferentes para os mesmos fatos na mesma semana. A ponte
#: fazia a projeção funcionar contra qualquer um dos dois, e era exatamente isso
#: que mantinha a ambiguidade viva: enquanto ela existisse, ninguém precisava
#: decidir qual schema era o real.
#:
#: O schema é `v9_01_trafego_inventario.sql`, e só ele. A ponte saiu.
COLUNAS_DA_CONTA = {
    "tentativa_em": "lido_em",
    "tentativa_resultado": "resultado",
    "tentativa_motivo": "motivo",
    "tentativa_duracao_ms": "duracao_ms",
    "leitura_boa_em": "ultima_leitura_boa_em",
    "leitura_boa_campanhas": "lidas",
    "leitura_boa_duracao_ms": "duracao_boa_ms",
}


def normalizar_linha_de_conta(bruta: Dict[str, Any]) -> Dict[str, Any]:
    """Uma linha de `trafego_snapshot_conta` no vocabulário interno.

    Idempotente: chamar duas vezes dá o mesmo resultado, porque a linha já
    normalizada não tem mais as chaves de origem. É o que permite as funções
    deste módulo normalizarem por conta própria sem coordenação.
    """
    saida = dict(bruta)
    for coluna, interno in COLUNAS_DA_CONTA.items():
        if coluna in bruta:
            saida[interno] = bruta[coluna]
    return saida


# ── porta de leitura ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlanoDeConsulta:
    """O que a fonte precisa saber para resolver a página NO BANCO.

    As contas já vêm separadas em duas listas porque a regra de presença muda
    conforme a conta foi lida ou não:

      · conta que FALHOU  → todas as campanhas dela valem como
        `sincronizacao_falhou`, e o filtro de presença armazenada não se aplica;
      · conta que foi LIDA → o filtro de presença armazenada vale normalmente.

    Sem essa separação, filtrar por `sincronizacao_falhou` teria de acontecer em
    Python depois de baixar tudo — que é exatamente o que "filtros resolvidos no
    banco" existe para impedir.
    """

    filtros: FiltrosDoInventario
    contas_lidas: Tuple[str, ...]
    contas_falhas: Tuple[str, ...]
    limite: int = LIMITE_PADRAO
    #: `(customer_id, ordem_operacional, volc_campaign_id)` — as três colunas do
    #: `ORDER BY`, na mesma ordem. Ver `gerar_cursor`.
    depois_de: Optional[Tuple[str, int, str]] = None

    @property
    def vazio(self) -> bool:
        return not self.contas_lidas and not self.contas_falhas


class FonteDeInventario(Protocol):
    """A porta. Quem a implementa fala com o snapshot, nunca com o Google.

    ## O contrato com o schema canônico

    A implementação (`app/trafego/persistencia.py`, Frente A) só pode tocar as
    tabelas de `supabase/migrations/v9_01_trafego_inventario.sql`. O mapeamento
    é este, e ele está escrito aqui porque a porta é o lugar onde as duas
    frentes se encontram:

    · `contas()`   → `trafego_snapshot_conta`, uma linha por conta.
      Colunas: `customer_id`, `nome`, `tentativa_em`, `tentativa_resultado`,
      `tentativa_motivo`, `tentativa_duracao_ms`, `leitura_boa_em`,
      `leitura_boa_campanhas`, `leitura_boa_duracao_ms`.
      ⚠️ **Ausência de linha é informação**: conta descoberta e nunca varrida
      NÃO tem linha, e a projeção a chama de `nunca_lido`. Não inventar uma
      linha com zeros é parte do contrato.

    · `campanhas()` → `trafego_campanha` (identidade) junto de
      `trafego_campanha_espelho` (leitura) e `trafego_vinculo` (decisão).
      A separação em duas tabelas é o conserto de E-08 e não pode ser desfeita
      numa view "para facilitar": dado DECLARADO e dado ESPELHADO não dividem
      tabela, então nenhum gatilho de espelho alcança uma declaração.
      A linha devolvida é o achatamento das três, com os nomes que
      `campanha_projetada()` lê — incluindo `presenca` NULA quando não há
      ressalva. Campanha SEM linha de espelho existe e tem de aparecer: é uma
      identidade declarada que nenhuma varredura confirmou ainda.

    · `contagem()` → total por `customer_id`, DEPOIS dos filtros e ANTES da
      paginação. É o número que a tela mostra no cabeçalho de cada conta.

    · `contagem_em_atencao()` → quantas linhas satisfazem `pede_atencao`.

    ## ⚠️ `atencao` não é coluna — é predicado, e ele vem daqui

    A tabela antiga tinha um booleano gerado. O schema canônico não tem, e a
    condição passou a ser derivada em `dominio.pede_atencao`. Quem implementa
    a porta traduz ESTE predicado para o banco, sem reinventá-lo:

        conta_falhou                                → atenção
        espelho.presenca IS NOT NULL                → atenção
        estado_externo <> 'ENABLED'                 → não
        entrega_lida_em IS NULL                     → atenção
        impressoes = 0                              → atenção
        impressoes > 0 AND cliques = 0              → atenção
        resto                                       → não

    Traduzir e não reimplementar tem um teste: se a fonte e o domínio
    discordarem, a aba Atenção e o sino passam a contar coisas diferentes.

    ## O que NÃO pode acontecer aqui

    Nenhum filtro pode ser aplicado em Python depois da consulta. O limite corta
    ANTES do filtro, então filtrar depois faz a paginação pular linhas sem nada
    na resposta denunciar — que é o defeito que o cursor keyset existe para
    impedir.
    """

    async def contas(self, filtros: FiltrosDoInventario) -> List[Dict[str, Any]]:
        ...

    async def campanhas(self, plano: PlanoDeConsulta) -> List[Dict[str, Any]]:
        ...

    async def contagem(self, plano: PlanoDeConsulta) -> Dict[str, int]:
        """Total por `customer_id`, DEPOIS dos filtros e ANTES da paginação."""
        ...

    async def contagem_em_atencao(self, plano: PlanoDeConsulta) -> int:
        ...

    async def contagem_por_natureza(
            self, plano: PlanoDeConsulta) -> Tuple[int, int]:
        """`(operacionais, historicas)` sob os MESMOS filtros do operador.

        Duas contagens e não uma derivada da outra. Com `incluir_historico=false`
        o total do recorte já É o operacional, e seria tentador devolver só o
        histórico e somar. Mas com `incluir_historico=true` o total passa a ser a
        soma, e a tela precisaria saber em qual dos dois regimes está para
        interpretar o número — que é exatamente a derivação que o contrato de
        integração proíbe.

        Ambas ignoram `filtros.incluir_historico`: elas descrevem as duas
        naturezas do MESMO recorte de filtros, não o que está sendo listado.
        """
        ...


# ── montagem ────────────────────────────────────────────────────────────────


#: O degrau de ordenação da linha, com recuo seguro.
#:
#: A view calcula `ordem_operacional`; se a coluna faltar (view antiga, dublê
#: incompleto), `ORDEM_OUTROS_PRESENTES` é o recuo — um degrau do meio, que não
#: promove nem enterra. Zero seria pior: colocaria a linha no topo da fila de
#: atenção por acidente de ausência.
def _degrau(linha: Dict[str, Any]) -> int:
    bruto = linha.get("ordem_operacional")
    try:
        return int(bruto)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return dom.ORDEM_OUTROS_PRESENTES


def _iso(valor: Any) -> Optional[str]:
    d = _para_dt(valor)
    return d.astimezone(timezone.utc).isoformat() if d else None


def _vinculo(linha: Dict[str, Any]) -> Optional[VinculoDeFunil]:
    """`None` quando não há vínculo — e a tela mostra "sem vínculo", que é um
    estado de primeira classe, não um campo em branco."""
    opp = linha.get("opportunity_id")
    proj = linha.get("project_id")
    por = linha.get("vinculo_confirmado_por")
    if opp is None and proj is None and not por:
        return None
    return VinculoDeFunil(
        opportunity_id=int(opp) if opp is not None else None,
        project_id=int(proj) if proj is not None else None,
        confirmado_por=str(por) if por else None,
        confirmado_em=_iso(linha.get("vinculo_confirmado_em")),
    )


def _inteiro(v: Any) -> Optional[int]:
    """`None` sobrevive. Zero sobrevive. Um não é convertido no outro."""
    return dom.inteiro_ou_nulo(v)


def campanha_projetada(linha: Dict[str, Any], *, conta_falhou: bool,
                       agora: Optional[datetime] = None) -> CampanhaNoInventario:
    """Uma linha do snapshot virando a forma do contrato.

    ⚠️ Quando a conta nunca foi lida com sucesso, os números da campanha NÃO
    saem: sem `entrega_lida_em` não há como carimbá-los, e `Entrega` recusa
    número sem carimbo. É a regra A aplicada onde ela costuma escapar — a linha,
    não só o envelope.
    """
    entrega_lida = leitura_de(linha.get("entrega_lida_em"), agora)
    if entrega_lida is None:
        entrega = Entrega(moeda=linha.get("moeda") or None)
    else:
        entrega = Entrega(
            impressoes=_inteiro(linha.get("impressoes")),
            cliques=_inteiro(linha.get("cliques")),
            custo_micros=_inteiro(linha.get("custo_micros")),
            moeda=linha.get("moeda") or None,
            leitura=entrega_lida,
        )

    estrategia = estrategia_canonica(linha.get("estrategia"))
    lance = _inteiro(linha.get("lance_micros"))
    verba = _inteiro(linha.get("verba_diaria_micros"))
    cockpit_id = linha.get("cockpit_campaign_id")

    return CampanhaNoInventario(
        volc_campaign_id=str(linha.get("volc_campaign_id") or ""),
        campaign_lineage_id=(str(linha["campaign_lineage_id"])
                             if linha.get("campaign_lineage_id") else None),
        externa=IdentidadeExterna(
            customer_id=str(linha.get("customer_id") or SEM_CONTA),
            campaign_id=str(linha.get("campaign_id") or ""),
        ),
        nome=str(linha.get("nome") or ""),
        estado_externo=(str(linha["estado_externo"])
                        if linha.get("estado_externo") else None),
        veiculacao=(str(linha["veiculacao"]) if linha.get("veiculacao") else None),
        canal=canal_canonico(linha.get("canal")),
        estrategia=estrategia,
        lance_micros=lance,
        verba_diaria_micros=verba,
        teto_de_cliques=teto_de_cliques(verba, lance, estrategia),
        entrega=entrega,
        vinculo=_vinculo(linha),
        procedencia=(str(linha.get("procedencia") or DESCONHECIDA)
                     if str(linha.get("procedencia") or "") in PROCEDENCIAS
                     else DESCONHECIDA),
        presenca=presenca_efetiva(str(linha.get("presenca") or ""), conta_falhou),
        # Só quando o mapeamento é seguro: o cockpit legado endereça pela chave
        # INTERNA de `campaigns`, e derivá-la do `campaign_id` externo mandaria
        # o operador para a campanha de outra pessoa.
        cockpit_href=(f"/dashboard/campaign/{cockpit_id}" if cockpit_id else None),
    )


async def montar_inventario(
    fonte: FonteDeInventario,
    filtros: FiltrosDoInventario,
    *,
    limite: int = LIMITE_PADRAO,
    cursor: Optional[str] = None,
    agora: Optional[datetime] = None,
) -> Inventario:
    """A projeção completa, a partir do snapshot. Não faz rede para o Google.

    A ordem importa: primeiro as contas (é o resultado da varredura delas que
    decide o que a presença de cada campanha significa), depois a página de
    campanhas, depois as contagens. As três chamadas são da FONTE — nenhum
    filtro é aplicado em Python aqui.
    """
    agora = agora or datetime.now(timezone.utc)
    limite = max(1, min(int(limite or LIMITE_PADRAO), LIMITE_MAXIMO))

    linhas_de_conta = await fonte.contas(filtros)

    faltou: List[Faltou] = []
    lidas: List[str] = []
    falhas: List[str] = []
    estado: Dict[str, Dict[str, Any]] = {}

    for bruta in linhas_de_conta:
        c = normalizar_linha_de_conta(bruta)
        cid = str(c.get("customer_id") or "")
        if not cid:
            continue
        f = frescor_da_conta(c, agora)
        estado[cid] = {"linha": c, "frescor": f}
        if f == FALHOU:
            falhas.append(cid)
            faltou.append(Faltou(
                customer_id=cid,
                escopo="conta",
                motivo=str(c.get("motivo") or
                           "a última varredura desta conta falhou; o dado abaixo "
                           "é o último snapshot bom"),
            ))
        else:
            lidas.append(cid)
            if f == PARCIAL:
                faltou.append(Faltou(
                    customer_id=cid,
                    # O escopo do que faltou viaja DENTRO do motivo: o schema
                    # canônico tem uma coluna de texto para a tentativa, não duas.
                    escopo="conta",
                    motivo=str(c.get("motivo") or
                               "parte da varredura desta conta não voltou"),
                ))

    # Presença pedida explicitamente muda quais contas entram: uma conta que
    # falhou só contribui se `sincronizacao_falhou` estiver no filtro, e uma
    # conta lida nunca produz esse estado.
    if filtros.presenca:
        if SINCRONIZACAO_FALHOU not in filtros.presenca:
            falhas = []
        if set(filtros.presenca) == {SINCRONIZACAO_FALHOU}:
            lidas = []

    # ── frescor: filtro de CONTA, aplicado sobre o conjunto de contas ───────
    #
    # ⚠️ Ele foi aceito, validado e IGNORADO por três rodadas: nenhum consumidor
    # o lia. Um filtro que a API valida e descarta é pior que um filtro que não
    # existe — quem o manda recebe 200 com a lista inteira e conclui que não há
    # nada para filtrar, quando na verdade ninguém filtrou.
    #
    # Ele entra AQUI, e não em `params_de_campanhas`, porque frescor é
    # propriedade da CONTA e não da campanha: ele sai de
    # `trafego_snapshot_conta`, já foi calculado logo acima por
    # `frescor_da_conta()`, e a campanha não tem coluna que o carregue. Recortar
    # as contas antes de montar o plano faz o filtro chegar ao banco pelo
    # `customer_id.in.(…)` das famílias — resolvido no servidor, como todos os
    # outros.
    #
    # A pergunta que ele responde: *"mostre o que veio de leitura que falhou"*,
    # ou *"o que está velho"*. É a pergunta do operador que desconfia do número
    # antes de agir sobre ele.
    if filtros.frescor:
        querido = set(filtros.frescor)
        lidas = [c for c in lidas if estado[c]["frescor"] in querido]
        falhas = [c for c in falhas if estado[c]["frescor"] in querido]

    plano = PlanoDeConsulta(
        filtros=filtros,
        contas_lidas=tuple(lidas),
        contas_falhas=tuple(falhas),
        limite=limite,
        depois_de=ler_cursor(cursor, filtros) if cursor else None,
    )

    linhas: List[Dict[str, Any]] = [] if plano.vazio else await fonte.campanhas(plano)
    por_conta: Dict[str, int] = {} if plano.vazio else await fonte.contagem(plano)
    em_atencao = 0 if plano.vazio else await fonte.contagem_em_atencao(plano)
    operacionais, historicas = (
        (0, 0) if plano.vazio else await fonte.contagem_por_natureza(plano))

    # Uma linha a mais que o limite é como sabemos que há próxima página sem
    # pedir um COUNT do conjunto inteiro a cada requisição.
    tem_mais = len(linhas) > limite
    linhas = linhas[:limite]

    agrupadas: Dict[str, List[CampanhaNoInventario]] = {}
    falharam = set(falhas)
    for l in linhas:
        cid = str(l.get("customer_id") or SEM_CONTA)
        agrupadas.setdefault(cid, []).append(
            campanha_projetada(l, conta_falhou=cid in falharam, agora=agora))

    contas: List[ContaNoInventario] = []
    for cid in sorted(set(list(estado.keys()) + list(agrupadas.keys()))):
        bruta = estado.get(cid, {}).get("linha", {"customer_id": cid})
        f = estado.get(cid, {}).get("frescor", NUNCA_LIDO)
        contas.append(ContaNoInventario(
            customer_id=cid,
            nome=(str(bruta.get("nome")) if bruta.get("nome") else None),
            frescor=f,
            leitura=leitura_de(bruta.get("lido_em"), agora),
            ultima_leitura_boa=leitura_de(bruta.get("ultima_leitura_boa_em"), agora),
            motivo=(str(bruta.get("motivo")) if bruta.get("motivo") else None),
            quantidade=int(por_conta.get(cid, len(agrupadas.get(cid, [])))),
            campanhas=agrupadas.get(cid, []),
        ))

    proximo = None
    if tem_mais and linhas:
        ultima = linhas[-1]
        proximo = gerar_cursor(str(ultima.get("customer_id") or SEM_CONTA),
                               _degrau(ultima),
                               str(ultima.get("volc_campaign_id") or ""),
                               filtros)

    boas = [c.ultima_leitura_boa for c in contas if c.ultima_leitura_boa]
    envelope_leitura = max(boas, key=lambda l: l.idade_s) if boas else None

    return Inventario(
        versao=VERSAO_INVENTARIO,
        frescor=dom.frescor_do_conjunto([c.frescor for c in contas]),
        leitura=envelope_leitura,
        parcial=bool(faltou),
        faltou=faltou,
        contas=contas,
        proximo_cursor=proximo,
        totais={
            "contas": len(contas),
            # Operacional e histórico contados SEPARADAMENTE, e `geral` é a soma
            # — nunca um substituto. Um número só forçaria a tela a derivar o
            # outro, e derivar é onde os dois começam a discordar.
            #
            # Os três respeitam os MESMOS filtros do operador. `geral` não é o
            # universo do banco: é "tudo o que casa com o que você pediu,
            # incluindo história". Chamar de geral o universo faria a busca por
            # "FGTS" mostrar `geral: 84`.
            "operacionais": operacionais,
            "historicas": historicas,
            "geral": operacionais + historicas,
            "atencao": em_atencao,
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# A PORTA DE PERSISTÊNCIA — e o defeito que ela fecha
#
# Aqui vivia `FonteSupabase`, uma classe que montava query params do PostgREST
# contra `volc_trafego_conta` e `volc_trafego_campanha`. Essas duas tabelas
# NÃO EXISTEM: nenhuma migration deste repositório as cria, e o schema canônico
# do inventário (`supabase/migrations/v9_01_trafego_inventario.sql`) tem outras
# seis, com outros nomes e outra modelagem.
#
# Contra o banco real, toda requisição de leitura devolvia 404 do PostgREST. A
# suíte passava porque a fonte era dublada em 100% dos testes — o que prova a
# projeção e não prova o acesso. Um teste que só exercita o dublê mede a nossa
# imaginação sobre o banco, não o banco.
#
# A classe foi REMOVIDA em vez de reapontada. Reapontá-la criaria uma segunda
# implementação de acesso concorrendo com a que a Frente A entrega em
# `app/trafego/persistencia.py`, e duas camadas de acesso ao mesmo schema
# divergem exatamente como as duas regras de frescor divergiram.
#
# O que fica no lugar é a PORTA (`FonteDeInventario`, acima, com o mapeamento
# tabela a tabela documentado) e UMA função de fábrica — o ponto de troca.
# ═══════════════════════════════════════════════════════════════════════════

#: O schema canônico. Existe como constante para o teste de gate poder afirmar
#: que nenhum nome de tabela fantasma sobrou no módulo.
SCHEMA_CANONICO = "supabase/migrations/v9_01_trafego_inventario.sql"

#: As tabelas que a implementação da porta pode tocar, e nada além delas.
TABELAS_DO_INVENTARIO: Tuple[str, ...] = (
    "trafego_linhagem",
    "trafego_campanha",
    "trafego_campanha_espelho",
    "trafego_snapshot_conta",
    "trafego_vinculo",
    "trafego_evento",
)


class PersistenciaAusente(RuntimeError):
    """Não há implementação de acesso ao snapshot instalada.

    Erro alto e claro, e nunca uma lista vazia: lista vazia é um FATO deste
    domínio (`vazio_confirmado`), e devolver o fato quando a causa é a ausência
    de código é a definição de "parece que está tudo bem".
    """


def fabricar_fonte(base: str, chave: str) -> FonteDeInventario:
    """O ÚNICO ponto de troca entre a projeção e o acesso a dados.

    ⚠️ Ponto de integração declarado. A implementação vive em
    `app/trafego/persistencia.py` (Frente A) e não é importada no topo deste
    arquivo de propósito: o núcleo não pode depender da infraestrutura em tempo
    de carga, e o import tardio é o que mantém `inventario.py` importável — e
    testável — sem banco nenhum.

    Quando `persistencia.py` existir, esta função devolve a fonte dela. Enquanto
    não existir, ela LEVANTA com o nome do arquivo que falta. O silêncio seria
    pior: o defeito que esta rodada fecha é justamente uma camada de acesso que
    parecia existir.
    """
    try:
        from app.trafego import persistencia  # noqa: PLC0415
    except ImportError as exc:
        raise PersistenciaAusente(
            "não há camada de acesso ao snapshot: `app/trafego/persistencia.py` "
            f"não está instalada. O schema canônico é {SCHEMA_CANONICO} e a "
            "porta que ela precisa satisfazer é `inventario.FonteDeInventario`."
        ) from exc
    return persistencia.FonteDeInventarioSupabase(base, chave)
