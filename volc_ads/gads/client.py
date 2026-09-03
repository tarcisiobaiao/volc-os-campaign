"""Fábrica de clientes Google Ads + execução com retry tipado.

Uma única credencial (~/google-ads.yaml) atende todas as contas; o que muda
entre chamadas é o login_customer_id. Cacheamos por MCC para não recarregar
o YAML a cada query.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, TypeVar

from google.ads.googleads.client import GoogleAdsClient

from . import autoridade, modo
from .errors import Classe, FalhaGads, classificar

log = logging.getLogger("forge.gads")

VERSAO_API = "v25"

T = TypeVar("T")


@lru_cache(maxsize=32)
def cliente(login_customer_id: str, versao: str = VERSAO_API) -> GoogleAdsClient:
    """Cliente para operar sob um determinado manager (MCC)."""
    c = GoogleAdsClient.load_from_storage(version=versao)
    c.login_customer_id = str(login_customer_id)
    return c


@dataclass(frozen=True)
class PoliticaRetry:
    tentativas: int = 5
    base_s: float = 1.0
    teto_s: float = 60.0
    fator: float = 2.0
    jitter: float = 0.25

    def espera(self, tentativa: int, sugerido: float | None = None) -> float:
        """Backoff exponencial com jitter; respeita o delay sugerido pela API.

        O jitter não é enfeite: sem ele, N workers que tomam rate limit ao
        mesmo tempo voltam a bater ao mesmo tempo, e o throttle se perpetua.
        """
        if sugerido is not None:
            base = sugerido
        else:
            base = min(self.base_s * (self.fator**tentativa), self.teto_s)
        return base * (1 + random.uniform(-self.jitter, self.jitter))


class ErroTerminal(RuntimeError):
    """Falha que não deve ser retentada. Carrega a classificação completa."""

    def __init__(self, falha: FalhaGads):
        self.falha = falha
        super().__init__(falha.resumo())


class ErroEsgotado(RuntimeError):
    """Retentável, mas as tentativas acabaram."""

    def __init__(self, falha: FalhaGads, tentativas: int):
        self.falha = falha
        self.tentativas = tentativas
        super().__init__(f"esgotado após {tentativas} tentativas: {falha.resumo()}")


def executar(
    fn: Callable[[], T],
    *,
    politica: PoliticaRetry | None = None,
    rotulo: str = "",
) -> T:
    """Executa `fn` aplicando retry apenas onde retry faz sentido.

    TERMINAL sobe na hora — não gastamos cinco tentativas num payload inválido.
    THROTTLED espera o que a API mandou esperar.
    TRANSIENT usa backoff exponencial com jitter.
    """
    pol = politica or PoliticaRetry()
    ultima: FalhaGads | None = None

    for tentativa in range(pol.tentativas):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — reclassificamos abaixo
            falha = classificar(exc)
            ultima = falha

            if falha.classe is Classe.TERMINAL:
                log.error("[%s] terminal: %s", rotulo, falha.resumo())
                raise ErroTerminal(falha) from exc

            if tentativa == pol.tentativas - 1:
                break

            atraso = pol.espera(tentativa, falha.retry_apos_s)
            log.warning(
                "[%s] %s (tentativa %d/%d) — aguardando %.1fs: %s",
                rotulo,
                falha.classe.value,
                tentativa + 1,
                pol.tentativas,
                atraso,
                falha.resumo()[:180],
            )
            time.sleep(atraso)

    assert ultima is not None
    raise ErroEsgotado(ultima, pol.tentativas)


def buscar(
    customer_id: str,
    query: str,
    *,
    login_customer_id: str,
    politica: PoliticaRetry | None = None,
) -> Iterator[Any]:
    """search_stream com retry, materializado em lista.

    Materializar é deliberado: um gerador que estoura no meio do consumo não
    pode ser retentado sem duplicar o que já saiu. Preferimos pagar memória
    a devolver resultado parcial silenciosamente.
    """
    c = cliente(login_customer_id)
    servico = c.get_service("GoogleAdsService")

    def _rodar() -> list[Any]:
        linhas: list[Any] = []
        for lote in servico.search_stream(customer_id=str(customer_id), query=query):
            linhas.extend(lote.results)
        return linhas

    return iter(executar(_rodar, politica=politica, rotulo=f"buscar:{customer_id}"))


def validar_mutacoes(
    customer_id: str,
    operacoes: list[Any],
    *,
    login_customer_id: str,
) -> FalhaGads | None:
    """Submete o grafo de operações com validate_only=True.

    Devolve None se o payload é válido, ou a FalhaGads classificada.
    Nada é criado — este é o teste que custa zero e roda contra a conta real.

    Deliberadamente NÃO exige destravar a escrita: validate_only é leitura
    para todos os efeitos. A API valida e descarta.
    """
    c = cliente(login_customer_id)
    servico = c.get_service("GoogleAdsService")

    req = c.get_type("MutateGoogleAdsRequest")
    req.customer_id = str(customer_id)
    req.mutate_operations.extend(operacoes)
    req.validate_only = True
    req.partial_failure = False

    try:
        servico.mutate(request=req)
    except Exception as exc:  # noqa: BLE001
        return classificar(exc)
    return None


def mutar(
    customer_id: str,
    operacoes: list[Any],
    *,
    login_customer_id: str,
    autorizacao: autoridade.Autorizacao | None = None,
    canal: str = "",
    plano_impressao: str = "",
    politica: PoliticaRetry | None = None,
) -> Any:
    """Mutação REAL e atômica. Exige autorização de nascimento E trava aberta.

    Único caminho do forge capaz de alterar uma conta. As portas, em ordem:

      1. **autorização de nascimento** assinada, casada com conta, MCC, canal e
         plano — e CONSUMIDA aqui, para que a mesma autorização não escreva
         duas vezes;
      2. o payload manda a campanha nascer `PAUSED`, lido do próprio payload;
      3. a trava de dois fatores de `modo`.

    ⚠️ `autorizacao` tem default `None` por compatibilidade de assinatura, e
    `None` é RECUSA — nunca permissão. O default existe para que um chamador
    antigo receba `AutorizacaoAusente` com a mensagem inteira em vez de um
    `TypeError` que não diz onde a porta está.

    ⚠️ A ordem coloca a autorização ANTES da trava de propósito. A trava é
    global de processo: com ela aberta por uma escrita legítima em curso, um
    chamador sem autorização atravessaria a primeira porta se ela fosse a
    primeira. A autorização não depende do estado de ninguém.

    Use `validar_mutacoes()` para testar payload sem escrever: `validate_only`
    é leitura e continua sem exigir autorização nenhuma.
    """
    # ⚠️ `canal` e `plano_impressao` vêm DE QUEM CHAMA, e não da autorização.
    # Ler os dois de dentro dela faria a conferência comparar cada campo com
    # ele mesmo — verde sempre, prova nenhuma. Quem chama declara o que acredita
    # estar escrevendo; a autorização diz o que foi autorizado; divergência
    # morre aqui. Vazio é divergência: `conferir` recusa contra o valor selado.
    plano_real = autoridade.impressao_das_operacoes(operacoes)
    if plano_impressao and str(plano_impressao).strip().lower() != plano_real:
        raise autoridade.AutorizacaoInvalida(
            "a impressão declarada pelo chamador não bate com os bytes das "
            "operações que seriam enviados. Nada foi enviado ao Google."
        )
    autoridade.exigir_e_consumir(
        autorizacao,
        conta=str(customer_id),
        mcc=str(login_customer_id),
        canal=canal,
        plano_impressao=plano_real,
    )
    autoridade.exigir_nascimento_pausado(operacoes)
    modo.exigir_leitura_apenas(f"mutar({customer_id}, {len(operacoes)} operações)")

    c = cliente(login_customer_id)
    servico = c.get_service("GoogleAdsService")

    req = c.get_type("MutateGoogleAdsRequest")
    req.customer_id = str(customer_id)
    req.mutate_operations.extend(operacoes)
    req.validate_only = False
    req.partial_failure = False

    return executar(
        lambda: servico.mutate(request=req),
        politica=politica,
        rotulo=f"mutar:{customer_id}",
    )
