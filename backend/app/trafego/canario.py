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


CONTA = "5478096539"
CONTA_FORMATADA = "547-809-6539"
NOME_DA_CONTA = "Portal Mundo Mais"
MCC = "6016739364"
CANAL = "SEARCH"

# Mesmo pausada, a campanha carrega uma configuração que alguém poderia ligar
# diretamente no painel do Google. Os tetos reduzem o pior caso desse erro.
ORCAMENTO_DIARIO_MAXIMO_BRL = Decimal("20.00")
CPC_MAXIMO_BRL = Decimal("1.00")

_IMPRESSAO = re.compile(r"^[0-9a-f]{64}$")
_CARIMBO_NOME = re.compile(r"^[0-9]{8}_[0-9]{6}$")


class CanarioRecusado(ValueError):
    """O pedido saiu da janela estreita autorizada para o canário."""


@dataclass(frozen=True)
class Politica:
    customer_id: str = CONTA
    customer_label: str = NOME_DA_CONTA
    login_customer_id: str = MCC
    canal: str = CANAL
    cria_pausada: bool = True
    inclui_ativacao: bool = False
    orcamento_diario_maximo_brl: str = str(ORCAMENTO_DIARIO_MAXIMO_BRL)
    cpc_maximo_brl: str = str(CPC_MAXIMO_BRL)

    def para_json(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "customer_id_formatado": CONTA_FORMATADA,
            "customer_label": self.customer_label,
            "login_customer_id": self.login_customer_id,
            "canal": self.canal,
            "cria_pausada": self.cria_pausada,
            "inclui_ativacao": self.inclui_ativacao,
            "orcamento_diario_maximo_brl": self.orcamento_diario_maximo_brl,
            "cpc_maximo_brl": self.cpc_maximo_brl,
        }


POLITICA = Politica()


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
    if str(canal or "").upper() != CANAL:
        raise CanarioRecusado(
            f"o primeiro canário opera apenas {CANAL}; recebido {canal!r}."
        )
    if not confirmar_criacao_pausada:
        raise CanarioRecusado(
            "faltou a confirmação explícita de criar uma campanha PAUSADA. "
            "Esta autorização não inclui ativação."
        )
    carimbo_do_nome(carimbo_nome)
    budget = _decimal(budget_diario, "orçamento diário")
    if budget > ORCAMENTO_DIARIO_MAXIMO_BRL:
        raise CanarioRecusado(
            f"orçamento diário de R$ {budget} supera o teto do canário "
            f"(R$ {ORCAMENTO_DIARIO_MAXIMO_BRL})."
        )
    cpc = _decimal(cpc_inicial, "CPC inicial")
    if cpc > CPC_MAXIMO_BRL:
        raise CanarioRecusado(
            f"CPC inicial de R$ {cpc} supera o teto do canário "
            f"(R$ {CPC_MAXIMO_BRL})."
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


def campanhas_com_destino(
    *, customer_id: str, login_customer_id: str, url_final: str,
    servico: Any = None,
) -> tuple[dict[str, str], ...]:
    """Recusa duplicidade por destino, mesmo que metadado mude a marca.

    O primeiro canário não precisa de duas campanhas Search PAUSED/ENABLED
    apontando para a mesma página. A leitura inclui anúncios porque, em Search,
    a URL final pertence ao anúncio e não à campanha.
    """
    alvo = str(url_final or "").strip().rstrip("/")
    if not alvo.startswith("https://"):
        raise CanarioRecusado("o canário exige URL final HTTPS para a prova de duplicidade.")
    if servico is None:
        from volc_ads.gads.client import cliente

        servico = cliente(login_customer_id).get_service("GoogleAdsService")
    consulta = (
        "SELECT campaign.id, campaign.name, campaign.status, "
        "ad_group_ad.ad.final_urls "
        "FROM ad_group_ad "
        "WHERE campaign.status != 'REMOVED' "
        "AND ad_group_ad.status != 'REMOVED'"
    )
    encontrados: dict[str, dict[str, str]] = {}
    for linha in servico.search(customer_id=str(customer_id), query=consulta):
        finais = tuple(str(u).strip().rstrip("/") for u in linha.ad_group_ad.ad.final_urls)
        if alvo not in finais:
            continue
        campanha = linha.campaign
        cid = str(campanha.id)
        encontrados[cid] = {
            "campaign_id": cid,
            "campaign_name": str(campanha.name),
            "status": str(getattr(campanha.status, "name", campanha.status)),
            "url_final": str(url_final),
        }
    return tuple(encontrados[k] for k in sorted(encontrados))
