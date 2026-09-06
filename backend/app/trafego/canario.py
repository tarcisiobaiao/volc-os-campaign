"""Política estreita do primeiro canário de criação Search.

Este módulo não é uma lista geral de contas autorizadas. Ele representa uma
janela operacional deliberadamente pequena: uma única conta-laboratório, um
único canal e criação sempre pausada. Ativar campanha é outro ato e não existe
neste fluxo.

O objetivo é que abrir a trava global de escrita não transforme todas as contas
da casa em alvo. Para este canário, as duas perguntas são independentes:

* a trava permite que o processo escreva agora? (`volc_ads.gads.modo`)
* este pedido é exatamente o canário autorizado aqui? (este módulo)
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

# ⚠️ A autoridade única de autorização de canal, do lado que o EXECUTOR também
# alcança. Stdlib pura — não arrasta o SDK do Google para o boot do backend.
from volc_ads import autorizacao_de_canal as aut


CONTA = "5478096539"
CONTA_FORMATADA = "547-809-6539"
NOME_DA_CONTA = "Portal Mundo Mais"
MCC = "6016739364"
CANAL = "SEARCH"

# Mesmo pausada, a campanha carrega uma configuração que alguém poderia ligar
# diretamente no painel do Google. Os tetos reduzem o pior caso desse erro.
ORCAMENTO_DIARIO_MAXIMO_BRL = Decimal("20.00")
CPC_MAXIMO_BRL = Decimal("1.00")

#: Tetos de verba diária por canal, em BRL.
#:
#: ⚠️ NÃO é o mesmo número repetido quatro vezes, e a diferença é medida, não
#: estética. Search entrega por clique num leilão que o CPC máximo já limita;
#: Display, Demand Gen e PMax entregam por impressão em inventário muito maior,
#: onde o teto de verba é o ÚNICO freio — não existe CPC para segurá-los. Um
#: canário desses gasta o dia inteiro de orçamento em minutos se o teto for o
#: de Search por descuido.
TETO_DIARIO_POR_CANAL: dict[str, Decimal] = {
    "SEARCH": ORCAMENTO_DIARIO_MAXIMO_BRL,
    "DISPLAY": Decimal("20.00"),
    "DEMAND_GEN": Decimal("20.00"),
    "PERFORMANCE_MAX": Decimal("20.00"),
}

#: Os canais cujo pedido carrega CPC e rede — quer dizer: Search, e só ele.
#:
#: ⚠️ Esta é a metade que mais importa desta tarefa. `cpc_inicial` e `rede`
#: NÃO são campos universais: `network_settings` de Display é fixo no builder,
#: Demand Gen escolhe canais por `channel_controls`, e PMax não tem controle
#: de rede nenhum (matriz §13). Cobrar "declare a rede" de um canal que não
#: tem rede a declarar produziria uma recusa que o operador não teria como
#: satisfazer — o mesmo defeito que a docstring de `elegivel` registra.
CANAIS_COM_CPC_E_REDE: frozenset[str] = frozenset({"SEARCH"})

#: Os canais que esta janela CONHECE. Conhecer não é autorizar: ver
#: `CANAIS_COM_CRIACAO_AUTORIZADA` logo abaixo.
CANAIS_DO_CANARIO: tuple[str, ...] = (
    "SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX")

#: Os canais cujo canário JÁ FOI autorizado — quer dizer: Search, e só ele.
#:
#: ⚠️ ESTE É O CONJUNTO QUE MANTÉM A CRIAÇÃO FECHADA, e separá-lo de
#: `CANAIS_DO_CANARIO` é o ponto inteiro da tarefa. Ter janela é ter teto,
#: capacidade e vocabulário; ter AUTORIZAÇÃO é outra coisa, e vem de um ato
#: humano separado por canal (o canário Display, o Demand Gen, o PMax — cada um
#: com seu runbook, nenhum executado aqui).
#:
#: ⚠️ **REFERÊNCIA, NÃO CÓPIA** (06/09/2026). A declaração mora em
#: `volc_ads/autorizacao_de_canal.py`, e a mudança não foi cosmética: até aqui a
#: trava existia SÓ neste módulo, que o executor não importa —
#: `volc_ads.subir.subir()` conhecia apenas `permite_mutacao_real`, e um script
#: in-process com a trava de escrita aberta criaria Display real sem passar por
#: esta janela. Uma trava que só existe num dos dois caminhos que chegam ao
#: `mutate` é uma convenção, não uma trava.
#:
#: `is` — e não `==` — é o que `test_trafego_canario.py` cobra: com um objeto
#: só, não há como os dois lados divergirem.
CANAIS_COM_CRIACAO_AUTORIZADA: frozenset[str] = aut.CANAIS_COM_CRIACAO_AUTORIZADA

_IMPRESSAO = re.compile(r"^[0-9a-f]{64}$")
_CARIMBO_NOME = re.compile(r"^[0-9]{8}_[0-9]{6}$")


class CanarioRecusado(ValueError):
    """O pedido saiu da janela estreita autorizada para o canário."""


@dataclass(frozen=True)
class Politica:
    """A janela do canário para UM canal.

    ⚠️ `canal` continua com default `SEARCH` e `POLITICA` continua sendo a
    política de Search. Quem já lia `canario.POLITICA` — a tela, o contrato de
    canais, os testes — continua lendo exatamente o que lia antes; o que mudou
    é que agora existe `politica_do_canal()` para os outros três.
    """

    customer_id: str = CONTA
    customer_label: str = NOME_DA_CONTA
    login_customer_id: str = MCC
    canal: str = CANAL
    #: ⚠️ O QUE ESTA JANELA CRIA, QUANDO CRIA — e ela só cria PAUSADA.
    #:
    #: Ele é `True` para os QUATRO canais, e virou `True` para os quatro em
    #: 06/09/2026. Até então ele carregava, sozinho, dois fatos que não são o
    #: mesmo: "esta janela nasce pausada" (contrato, sempre verdadeiro) e "este
    #: canal já tem canário aceito" (autorização, só Search). O colapso produzia
    #: a leitura mais perigosa possível na tela — `cria_pausada: false` em
    #: Display, Demand Gen e PMax —, que se lê como "então nasce ATIVA".
    #:
    #: Quem responde à segunda pergunta agora é `criacao_autorizada`, logo
    #: abaixo, e é ele que `exigir` consulta.
    cria_pausada: bool = True
    #: Este canal já teve o canário ACEITO? Ato humano separado, por canal, com
    #: runbook próprio. `False` não diz nada sobre como a campanha nasceria: diz
    #: que ela não nasce.
    criacao_autorizada: bool = True
    inclui_ativacao: bool = False
    orcamento_diario_maximo_brl: str = str(ORCAMENTO_DIARIO_MAXIMO_BRL)
    #: `None` quando o canal não tem CPC a declarar. ⚠️ Ausência NÃO é zero:
    #: zero significaria "o teto é R$ 0,00" e recusaria qualquer lance.
    cpc_maximo_brl: str | None = str(CPC_MAXIMO_BRL)
    #: Se este canal exige `rede` declarada. Só Search tem rede a declarar.
    exige_rede: bool = True

    def para_json(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "customer_id_formatado": CONTA_FORMATADA,
            "customer_label": self.customer_label,
            "login_customer_id": self.login_customer_id,
            "canal": self.canal,
            "cria_pausada": self.cria_pausada,
            "criacao_autorizada": self.criacao_autorizada,
            "inclui_ativacao": self.inclui_ativacao,
            "orcamento_diario_maximo_brl": self.orcamento_diario_maximo_brl,
            "cpc_maximo_brl": self.cpc_maximo_brl,
            "exige_rede": self.exige_rede,
        }


POLITICA = Politica()


def politica_do_canal(canal: Any) -> Politica:
    """A janela do canário para o canal pedido.

    Um canal fora da lista não devolve uma política frouxa: levanta. Devolver
    a de Search por omissão faria um pedido PMax herdar teto de CPC e exigência
    de rede que PMax não tem — e a recusa apareceria com o nome errado.
    """
    nome = str(canal or "").strip().upper()
    if nome not in CANAIS_DO_CANARIO:
        raise CanarioRecusado(
            f"o canário não tem política para o canal {canal!r}; "
            f"os canais com janela são {', '.join(CANAIS_DO_CANARIO)}."
        )
    if nome == CANAL:
        return POLITICA
    com_cpc = nome in CANAIS_COM_CPC_E_REDE
    return Politica(
        canal=nome,
        orcamento_diario_maximo_brl=str(TETO_DIARIO_POR_CANAL[nome]),
        cpc_maximo_brl=str(CPC_MAXIMO_BRL) if com_cpc else None,
        exige_rede=com_cpc,
        criacao_autorizada=nome in CANAIS_COM_CRIACAO_AUTORIZADA,
    )


def carimbo_do_nome(valor: Any = None) -> str:
    """Congela o carimbo que participa dos nomes do grafo provado.

    O construtor histórico produz um novo carimbo a cada chamada. Sem carregar
    o mesmo valor de ``/provar`` para ``/subir``, duas provas semanticamente
    iguais geram protobufs diferentes e o selo nunca pode conferir. O servidor
    cria o valor na primeira prova; o cliente apenas o devolve na aprovação.
    """
    carimbo = str(valor or datetime.now().strftime("%Y%m%d_%H%M%S"))
    if not _CARIMBO_NOME.fullmatch(carimbo):
        raise CanarioRecusado(
            "carimbo do plano inválido; rode a prova novamente antes de criar."
        )
    return carimbo


def _decimal(valor: Any, campo: str) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise CanarioRecusado(f"{campo} inválido: {valor!r}.") from exc
    if not numero.is_finite() or numero <= 0:
        raise CanarioRecusado(f"{campo} precisa ser maior que zero.")
    return numero


def impressao_do_plano(plano: Mapping[str, Any]) -> str:
    """Identidade estável de tudo que o humano revisou.

    Não usa o nome temporizado que o builder acrescenta ao payload: o instante
    é produzido pelo servidor e não é uma decisão do operador. Conta, canal,
    verba, lance, grupos, critérios, copy e destino estão todos no mapping.
    """
    canonico = json.dumps(
        plano, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def prefixo_da_marca(impressao: str) -> str:
    if not _IMPRESSAO.fullmatch(str(impressao or "")):
        raise CanarioRecusado("a impressão do plano não é um sha256 válido.")
    return f"VOLC-CANARY-{impressao[:12]}"


def exigir(
    *,
    customer_id: str,
    login_customer_id: str,
    canal: str,
    budget_diario: Any,
    cpc_inicial: Any,
    chave_intencao: str,
    carimbo_nome: Any,
    confirmar_criacao_pausada: bool,
    rede: Any = None,
) -> str:
    """Confere a janela do canário e devolve a marca remota determinística.

    ⚠️ `rede` é OBRIGATÓRIA aqui, e `None` é recusa — ao contrário do resto do
    sistema, onde `None` herda `REDE_LEGADA_SEARCH` para não mudar campanha
    antiga em silêncio. O canário não tem campanha antiga: ele é o primeiro
    lançamento com ledger v10 completo, e um lançamento cuja rede ninguém
    escolheu não prova o que ele existe para provar.
    """
    if str(customer_id) != CONTA or str(login_customer_id) != MCC:
        raise CanarioRecusado(
            f"esta janela cria somente na conta {CONTA_FORMATADA} "
            f"({NOME_DA_CONTA}), sob o MCC da VOLC. A conta recebida foi "
            f"{customer_id or '(ausente)'}."
        )
    politica = politica_do_canal(canal)
    if not confirmar_criacao_pausada:
        raise CanarioRecusado(
            "faltou a confirmação explícita de criar uma campanha PAUSADA. "
            "Esta autorização não inclui ativação."
        )
    carimbo_do_nome(carimbo_nome)
    budget = _decimal(budget_diario, "orçamento diário")
    teto = Decimal(politica.orcamento_diario_maximo_brl)
    if budget > teto:
        raise CanarioRecusado(
            f"orçamento diário de R$ {budget} supera o teto do canário "
            f"(R$ {teto})."
        )
    # ⚠️ TER JANELA NÃO É TER AUTORIZAÇÃO, e esta guarda vem DEPOIS das que
    # julgam o PLANO. Um pedido Display com verba acima do teto está errado
    # independentemente de autorização, e dizer primeiro "o canal não está
    # autorizado" esconderia o defeito que o operador consegue consertar.
    #
    # O canal ganhou teto, vocabulário e capacidades próprias; criar de verdade
    # continua dependendo do canário DAQUELE canal — ato humano separado, com
    # runbook próprio, ainda não executado.
    if not politica.criacao_autorizada:
        raise CanarioRecusado(
            f"o canário ainda não autoriza CRIAR em {politica.canal}: apenas "
            f"{', '.join(sorted(CANAIS_COM_CRIACAO_AUTORIZADA))} tem canário "
            f"aceito. Provar continua liberado; criar exige o canário do canal. "
            f"⚠️ Isto NÃO é uma dúvida sobre o estado inicial: quando este canal "
            f"criar, ele criará PAUSADO como todos os outros."
        )

    # ── CPC e rede: exclusivos de Search, e a exclusividade é o ponto ───────
    #
    # Display fixa `network_settings` no builder, Demand Gen escolhe canais por
    # `channel_controls` e PMax não tem controle de rede nenhum. Cobrar CPC ou
    # rede desses canais produziria uma recusa que o operador não teria como
    # satisfazer — e um teto de Search vazando para outro canal seria uma
    # política que ninguém mediu para o inventário dele.
    if politica.cpc_maximo_brl is None:
        return prefixo_da_marca(chave_intencao)
    cpc = _decimal(cpc_inicial, "CPC inicial")
    if cpc > Decimal(politica.cpc_maximo_brl):
        raise CanarioRecusado(
            f"CPC inicial de R$ {cpc} supera o teto do canário "
            f"(R$ {politica.cpc_maximo_brl})."
        )
    if rede is None:
        raise CanarioRecusado(
            "o canário exige a rede declarada (`rede`). Search Partners é "
            "inventário diferente do Google Search — outros sites, outro "
            "comportamento de consulta, outro CPC — e até 01/09/2026 ele "
            "nascia ligado sem ninguém escolher e sem aparecer no plano "
            "aprovado. Herdar isso calado num lançamento de prova seria provar "
            "outra coisa."
        )
    if getattr(rede, "search_partners", False):
        raise CanarioRecusado(
            "o canário roda com Search Partners DESLIGADO. Ele mede o "
            "comportamento do Google Search com um plano conhecido; misturar "
            "inventário de parceiros na primeira medição torna o resultado "
            "impossível de atribuir."
        )
    if getattr(rede, "display_expansion", False):
        raise CanarioRecusado(
            "o canário roda sem expansão para Display: ela troca o inventário "
            "sem trocar o tipo da campanha."
        )
    return prefixo_da_marca(chave_intencao)


def elegivel(
    *, customer_id: str, login_customer_id: str, canal: str,
    budget_diario: Any, cpc_inicial: Any, chave_intencao: str,
    carimbo_nome: Any, rede: Any = None,
) -> tuple[bool, str]:
    """Avalia a política na etapa de prova, sem fingir autorização humana.

    ⚠️ `rede` precisa ATRAVESSAR daqui para `exigir`. Quando a rede entrou na
    janela do canário, esta função continuou sem o parâmetro e passou a devolver
    sempre `False` — a tela lê `elegivel` para liberar o botão de criar, então o
    fluxo do operador ficou bloqueado por uma regra que ele não tinha como
    satisfazer. Uma guarda nova que esquece o caminho de leitura vira negação
    universal, que é indistinguível de estar quebrada.
    """
    try:
        exigir(
            customer_id=customer_id,
            login_customer_id=login_customer_id,
            canal=canal,
            budget_diario=budget_diario,
            cpc_inicial=cpc_inicial,
            chave_intencao=chave_intencao,
            carimbo_nome=carimbo_nome,
            confirmar_criacao_pausada=True,
            rede=rede,
        )
    except CanarioRecusado as exc:
        return False, str(exc)
    return True, "pedido dentro da política estreita do canário"


def campanhas_com_marca(
    *, customer_id: str, login_customer_id: str, marca: str, servico: Any = None,
) -> tuple[dict[str, str], ...]:
    """Busca read-only antes do mutate; falha de leitura nunca libera criação.

    A marca só aceita nosso alfabeto fechado, portanto pode entrar no literal
    GAQL sem transformar conteúdo do usuário em consulta.
    """
    if not re.fullmatch(r"VOLC-CANARY-[0-9a-f]{12}", marca):
        raise CanarioRecusado(f"marca de idempotência inválida: {marca!r}.")
    if servico is None:
        from volc_ads.gads.client import cliente

        servico = cliente(login_customer_id).get_service("GoogleAdsService")
    consulta = (
        "SELECT campaign.id, campaign.name, campaign.status "
        "FROM campaign "
        f"WHERE campaign.name LIKE '{marca}%'"
    )
    encontrados: list[dict[str, str]] = []
    for linha in servico.search(customer_id=str(customer_id), query=consulta):
        campanha = linha.campaign
        encontrados.append({
            "campaign_id": str(campanha.id),
            "campaign_name": str(campanha.name),
            "status": str(getattr(campanha.status, "name", campanha.status)),
        })
    return tuple(encontrados)


#: Onde mora a URL final de cada canal. NÃO é o mesmo lugar, e tratar como se
#: fosse foi um defeito real: `ad_group_ad` era consultado para todo canal, e
#: PMax NÃO TEM ad group. A consulta voltava vazia sempre, e vazio era lido
#: como "não há duplicidade" — quer dizer, a prova de destino de PMax nunca
#: provou nada.
#:
#: Cada entrada declara a tabela GAQL, o campo de URL e o filtro de estado.
_AUTORIDADE_DE_URL: dict[str, dict[str, str]] = {
    "SEARCH": {
        "de": "ad_group_ad",
        "campo": "ad_group_ad.ad.final_urls",
        "filtro": "AND ad_group_ad.status != 'REMOVED'",
    },
    "DISPLAY": {
        "de": "ad_group_ad",
        "campo": "ad_group_ad.ad.final_urls",
        "filtro": "AND ad_group_ad.status != 'REMOVED'",
    },
    "DEMAND_GEN": {
        "de": "ad_group_ad",
        "campo": "ad_group_ad.ad.final_urls",
        "filtro": "AND ad_group_ad.status != 'REMOVED'",
    },
    # ⚠️ PMax não tem ad group nem anúncio. A URL vive no asset group, e é ele
    # que precisa ser lido — a mesma matriz §1 que impede o builder de emitir
    # `ad_group_operation`.
    "PERFORMANCE_MAX": {
        "de": "asset_group",
        "campo": "asset_group.final_urls",
        "filtro": "AND asset_group.status != 'REMOVED'",
    },
}

#: Teto de páginas da leitura de duplicidade. Bater no teto NÃO é "não
#: encontrei": é leitura incompleta, e leitura incompleta bloqueia.
MAXIMO_DE_PAGINAS_DE_DESTINO = 50


class LeituraDeDestinoIncompleta(CanarioRecusado):
    """A leitura não terminou. ⚠️ Isto NÃO é prova de ausência de duplicidade."""


def campanhas_com_destino(
    *, customer_id: str, login_customer_id: str, url_final: str,
    canal: str = CANAL, servico: Any = None,
) -> tuple[dict[str, str], ...]:
    """Recusa duplicidade por destino, mesmo que metadado mude a marca.

    ⚠️ A AUTORIDADE DE URL É POR CANAL. Search, Display e Demand Gen guardam a
    URL final no ANÚNCIO; Performance Max não tem anúncio nem ad group e a
    guarda no ASSET GROUP. Até esta correção a consulta era sempre
    `FROM ad_group_ad`, então para PMax ela voltava vazia — sempre — e o vazio
    era lido como "não há campanha com este destino". A prova de duplicidade de
    PMax não provava nada, e provar nada em silêncio é pior que não provar.

    ⚠️ E leitura incompleta NÃO é ausência. O pager para no teto, e bater no
    teto levanta `LeituraDeDestinoIncompleta` em vez de devolver a lista
    parcial: uma lista parcial seria indistinguível de "conta limpa" para quem
    chama, e é justamente essa confusão que libera a segunda campanha.
    """
    alvo = str(url_final or "").strip().rstrip("/")
    if not alvo.startswith("https://"):
        raise CanarioRecusado("o canário exige URL final HTTPS para a prova de duplicidade.")
    nome_do_canal = str(canal or "").strip().upper()
    autoridade = _AUTORIDADE_DE_URL.get(nome_do_canal)
    if autoridade is None:
        raise CanarioRecusado(
            f"não sei onde {nome_do_canal or '(canal ausente)'} guarda a URL final, "
            f"então não sei provar duplicidade de destino nele."
        )
    if servico is None:
        from volc_ads.gads.client import cliente

        servico = cliente(login_customer_id).get_service("GoogleAdsService")
    consulta = (
        "SELECT campaign.id, campaign.name, campaign.status, "
        f"{autoridade['campo']} "
        f"FROM {autoridade['de']} "
        "WHERE campaign.status != 'REMOVED' "
        f"{autoridade['filtro']}"
    )
    caminho = autoridade["campo"].split(".")
    encontrados: dict[str, dict[str, str]] = {}
    lidas = 0
    for linha in servico.search(customer_id=str(customer_id), query=consulta):
        lidas += 1
        if lidas > MAXIMO_DE_PAGINAS_DE_DESTINO * 1000:
            raise LeituraDeDestinoIncompleta(
                "a leitura de duplicidade por destino passou do teto seguro sem "
                "terminar. Isto NÃO prova que não existe campanha com o mesmo "
                "destino — a parte não lida da conta pode conter uma."
            )
        alvo_lido: Any = linha
        for pedaco in caminho:
            alvo_lido = getattr(alvo_lido, pedaco, None)
            if alvo_lido is None:
                break
        finais = tuple(
            str(u).strip().rstrip("/") for u in (alvo_lido or ()))
        if alvo not in finais:
            continue
        campanha = linha.campaign
        cid = str(campanha.id)
        encontrados[cid] = {
            "campaign_id": cid,
            "campaign_name": str(campanha.name),
            "status": str(getattr(campanha.status, "name", campanha.status)),
            "url_final": str(url_final),
            "canal": nome_do_canal,
            "autoridade_de_url": autoridade["de"],
        }
    return tuple(encontrados[k] for k in sorted(encontrados))
