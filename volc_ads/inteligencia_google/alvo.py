"""Alvo canonico explicito da coleta one-shot de inteligencia Google Ads.

Camada de dominio: sem HTTP, sem Google Ads, sem Supabase, sem relogio. Aqui
mora apenas a regra de QUEM pode ser coletado sob demanda e o que a doutrina
oficial autoriza concluir sobre ele.

## Por que este modulo existe

A coleta continua parte de ``persistencia.campanhas_search_ativas``, que filtra
``estado_externo = ENABLED``. Uma campanha PAUSED — que e exatamente o que um
canario recem-criado e — nunca aparece na observabilidade, e a ausencia nao se
distingue de "coletamos e nao havia nada".

Abrir o filtro do scan continuo resolveria pelo lado errado: ampliaria a agenda
continua e a conta pagaria por campanhas que ninguem pediu. O caminho certo e
nomear o alvo. Uma execucao, um alvo, por identidade canonica interna E ID
externo E conta — os tres, explicitos.

⚠️ Este modulo NAO decide autoridade de agenda. Hoje ha duas candidatas — os
workflows n8n, onde a ingestao operacional ja vive, e o pacote systemd
versionado em ``deploy/google-intelligence/``, que nunca foi instalado — e
escolher UMA e justamente o que falta em P09-T14. O caminho por alvo nao entra
nessa disputa: ele nao tem relogio, nao tem loop e nao se agenda.

## Fail-closed e a regra

Identidade malformada, campanha inexistente, resultado ambiguo, conta divergente
ou canal ilegivel levantam excecao ANTES da primeira chamada ao Google Ads.
Nenhum recibo e gravado para um alvo que nao pode ser provado: um recibo falso e
pior que recibo nenhum, porque parece observabilidade.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

# Marca de procedencia gravada no payload dos recibos deste caminho. Nao entra
# na chave de idempotencia (ver modelo.DocumentoColeta.serializar), entao repetir
# o one-shot continua devolvendo o mesmo recibo.
ORIGEM_ALVO = "alvo_explicito"

CANAL_COM_PLANO_DE_PALAVRAS = "SEARCH"

# GenerateRecommendations e GenerateKeywordForecastMetrics sao montados a partir
# de ad_group_info/keywords — sao consultas de plano de palavras. Fora de SEARCH
# nao existe a pergunta, e "nao existe a pergunta" e NAO_SUPORTADO, nao vazio.
FAMILIAS_QUE_EXIGEM_PLANO_DE_PALAVRAS = ("RECOMENDACOES_GERADAS", "FORECAST_KEYWORDS")

# O vocabulario canonico de canal (ADR-18, `trafego_espelho_canal_canonico`)
# admite estes dois, e os dois significam "a conta nao disse qual e" — nunca
# "nao e SEARCH". Concluir NAO_SUPORTADO a partir deles seria ignorancia virando
# conclusao de dominio, com quantidade nula, sem erro e sem ninguem reprocessar.
CANAIS_SEM_INFORMACAO = ("UNSPECIFIED", "UNKNOWN")

MOTIVO_SIMULACAO_SEM_HISTORICO = (
    "simulacao de lance exige desempenho passado; a campanha nasceu dentro da "
    "janela observada e nao veiculou nela"
)

_CONTA = re.compile(r"^[0-9]{6,12}$")
_ID_EXTERNO = re.compile(r"^[0-9]{1,20}$")
# Identico a CHECK de `trafego_campanha.volc_campaign_id` (v9_01), inclusive na
# caixa. Rebaixar para minusculo aqui produziria um filtro PostgREST que nao
# casa com uma PK case-sensitive: a campanha existe e a resposta seria "nenhuma
# campanha no inventario" — afirmacao de ausencia sobre algo que esta la.
_ID_INTERNO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class ErroAlvoInvalido(ValueError):
    """A identidade pedida nao e sequer bem formada."""


class ErroAlvoDivergente(RuntimeError):
    """A identidade e bem formada, mas nao resolve para exatamente uma campanha."""


def normalizar_conta(valor: Any, campo: str = "customer_id") -> str:
    if not isinstance(valor, str):
        raise ErroAlvoInvalido(f"{campo} deve ser string")
    normalizado = "".join(ch for ch in valor if not ch.isspace() and ch != "-")
    if not (normalizado.isascii() and _CONTA.fullmatch(normalizado)):
        raise ErroAlvoInvalido(f"{campo} deve conter entre 6 e 12 digitos ASCII")
    return normalizado


def normalizar_id_externo(valor: Any, campo: str = "campaign_id") -> str:
    if not isinstance(valor, str):
        raise ErroAlvoInvalido(f"{campo} deve ser string")
    normalizado = valor.strip()
    if not (normalizado.isascii() and _ID_EXTERNO.fullmatch(normalizado)):
        raise ErroAlvoInvalido(f"{campo} deve conter entre 1 e 20 digitos ASCII")
    return normalizado


def normalizar_id_interno(valor: Any, campo: str = "volc_campaign_id") -> str:
    """Preserva a caixa: a coluna e PK textual case-sensitive no Postgres."""

    if not isinstance(valor, str):
        raise ErroAlvoInvalido(f"{campo} deve ser string")
    normalizado = valor.strip()
    if not _ID_INTERNO.fullmatch(normalizado):
        raise ErroAlvoInvalido(f"{campo} possui formato invalido")
    return normalizado


@dataclass(frozen=True)
class AlvoColeta:
    """Conta + identidade canonica interna + ID externo. Os tres obrigatorios.

    Nao ha default e nao ha ``None``: identidade interna e externa viajam juntas
    (mesma regra de ``modelo.DocumentoColeta``), e sem a conta nao ha como provar
    que o ID externo pertence a quem o pediu.
    """

    customer_id: str
    volc_campaign_id: str
    campaign_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "customer_id", normalizar_conta(self.customer_id))
        object.__setattr__(
            self, "volc_campaign_id", normalizar_id_interno(self.volc_campaign_id)
        )
        object.__setattr__(self, "campaign_id", normalizar_id_externo(self.campaign_id))


def _observado(valor: Any, campo: str, normalizador) -> str:
    if valor is None:
        raise ErroAlvoDivergente(f"inventario devolveu {campo} ausente para o alvo")
    try:
        return normalizador(str(valor), campo)
    except ErroAlvoInvalido as exc:
        raise ErroAlvoDivergente(f"inventario devolveu {campo} ilegivel: {exc}") from exc


def conferir_identidade_devolvida(alvo: AlvoColeta, registro: Any) -> str:
    """Confere campo a campo o que o inventario devolveu e retorna o canal.

    O filtro da consulta nao e prova: quem responde e um servico remoto, e um
    filtro ignorado devolveria a campanha errada com a mesma cara. A unica
    defesa e reconferir a identidade recebida contra a pedida.
    """

    if isinstance(registro, Mapping):
        ler = registro.get
    else:
        def ler(campo: str) -> Any:
            return getattr(registro, campo, None)

    for campo, esperado, normalizador in (
        ("customer_id", alvo.customer_id, normalizar_conta),
        ("volc_campaign_id", alvo.volc_campaign_id, normalizar_id_interno),
        ("campaign_id", alvo.campaign_id, normalizar_id_externo),
    ):
        atual = _observado(ler(campo), campo, normalizador)
        if atual != esperado:
            raise ErroAlvoDivergente(
                f"{campo} divergente: pedido {esperado}, inventario {atual}"
            )

    canal = ler("canal")
    if not isinstance(canal, str) or not canal.strip():
        raise ErroAlvoDivergente("inventario devolveu canal ausente para o alvo")
    normalizado = canal.strip().upper()
    if normalizado in CANAIS_SEM_INFORMACAO:
        # Fail-closed de proposito. Sem canal nao da para dizer quais familias
        # se aplicam, e o vocabulario de estados nao tem "nao sei": inventar
        # NAO_SUPORTADO ou INELEGIVEL aqui seria afirmar mais do que se sabe.
        raise ErroAlvoDivergente(
            f"inventario devolveu canal {normalizado}: nao se sabe o canal da "
            f"campanha, entao nao se sabe quais familias se aplicam"
        )
    return normalizado


def familias_nao_suportadas(canal: str) -> tuple[str, ...]:
    """Familias que nao existem fora de SEARCH — nao suportadas, nao vazias."""

    normalizado = canal.strip().upper()
    if normalizado in CANAIS_SEM_INFORMACAO or not normalizado:
        raise ErroAlvoDivergente(
            f"canal {normalizado or 'ausente'} nao autoriza conclusao de suporte"
        )
    if normalizado == CANAL_COM_PLANO_DE_PALAVRAS:
        return ()
    return FAMILIAS_QUE_EXIGEM_PLANO_DE_PALAVRAS


def motivo_nao_suportado(canal: str) -> str:
    return (
        f"familia depende de plano de palavras-chave; canal {canal.strip().upper()} "
        f"nao e {CANAL_COM_PLANO_DE_PALAVRAS}"
    )


def simulacao_elegivel(
    *,
    veiculou_na_janela: bool | None,
    inicio_da_campanha: date | None,
    janela_inicio: date,
) -> bool | None:
    """Decide se faz sentido esperar simulacao de lance para esta campanha.

    Doutrina oficial (``docs/architecture/evidence/GOOGLE-ADS-DOCS-2026-09-01.md``,
    secao 4): "Bid simulations are based on past performance", "You must have an
    established criterion, ad group, or campaign", "The time range is always in
    the past". Logo, campanha sem desempenho passado nao e elegivel — e ausencia
    de simulacao ali e conclusao valida, nao vazio observado.

    So devolve ``False`` quando isso e demonstravel: a janela precisa cobrir a
    VIDA INTEIRA da campanha e nao ter veiculacao. Se a campanha comecou antes da
    janela, pode haver historico que nao olhamos — devolve ``None``, e o coletor
    mantem o comportamento conservador de ``vazio_confirmado``.
    """

    if veiculou_na_janela:
        return True
    if veiculou_na_janela is None or inicio_da_campanha is None:
        return None
    if inicio_da_campanha < janela_inicio:
        return None
    return False
