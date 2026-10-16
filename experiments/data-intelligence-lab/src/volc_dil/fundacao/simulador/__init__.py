"""Simulator Lab da Fundação Data Intelligence (worker E, missão 2026-10-16).

Gerador determinístico (seed) de um mundo SINTÉTICO de arbitragem — Google Ads → site →
monetização JoinAds/GAM — por hora local, com um processo de OBSERVAÇÃO separado da verdade.

Fronteira: sem rede, sem segredo, sem Supabase/Google Ads/JoinAds reais; contas e ids são
sintéticos. Simulação NUNCA é prova de eficácia operacional: serve para testar contratos,
replay/shadow, modelos e observabilidade contra armadilhas conhecidas (gabarito disponível).

API pública estável (ver 07-SIMULATOR-LAB.md §6)::

    from volc_dil.fundacao.simulador import simular, cenario, NOMES
    sim = simular("zero_falso", seed=20261016, n_campanhas=6, n_dias=14)
    sim.mundo            # verdade (avaliação apenas)
    sim.leituras.registros   # list[RegistroObservacao] em ordem de available_at
    sim.leituras.gabarito    # obs_id -> Gabarito (avaliação apenas)

Relação com o código herdado: reaproveita ``volc_dil.contracts.fingerprint`` (JSON canônico,
sha256, versões, manifesto) e o contrato herdado via ``adaptador_contrato``; adota a técnica
de números aleatórios comuns por CDF inversa do ``volc_dil.swarm.simulador`` e a separação
verdade × emissão do ``volc_dil.replay.cenario``. Não duplica nem substitui aqueles mundos:
o swarm é por célula × ciclo e o replay v0 é campanha × dia em malha fechada com receita
α·gasto^b; este é campanha × hora × dispositivo com funil, leilão, orçamento e um observador
rico. O replay/shadow novo (worker D) pode fechar a malha re-simulando com
``orcamento_diario_micros`` (CRN garante o contrafactual pareado).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

import numpy as np

from .adaptador_contrato import para_observacao_contrato
from .calibracao import FAIXAS_FORMA, FONTES_PARAMETROS, medir_forma, verificar_forma
from .cenarios import ADVERSARIAIS, CATALOGO, NOMES, VERSAO_CATALOGO, catalogo_sha256, cenario
from .consumidor import chave_fato, soma_ingenua, somar_por_moeda, visao_as_of
from .mundo import METRICAS_HORARIAS, Campanha, Mundo, gerar_mundo, id_campanha, id_conta
from .observador import Leituras, iso, observar, registros_contrato
from .parametros import (
    DISPOSITIVOS,
    FONTES,
    PAISES,
    EspecCenario,
    JanelaForaDoAr,
    MudancaOrcamento,
    ParametrosMundo,
    ParametrosObservador,
    QuebraRegime,
)
from .registro import (
    CAMPOS_CONTRATO,
    CAMPOS_EXTRAS,
    STATUS,
    STATUS_COM_VALOR,
    STATUS_SEM_VALOR,
    Gabarito,
    RegistroObservacao,
)

VERSAO_SIMULADOR = "1.0.0"


@dataclass
class Simulacao:
    espec: EspecCenario
    seed: int
    mundo: Mundo
    leituras: Leituras


def simular(espec: Union[str, EspecCenario], seed: int, *, n_campanhas: Optional[int] = None,
            n_dias: Optional[int] = None, orcamento_diario_micros: Optional[np.ndarray] = None) -> Simulacao:
    """Gera mundo + observações de um cenário (nome do catálogo ou ``EspecCenario``)."""
    e = cenario(espec) if isinstance(espec, str) else espec
    if n_campanhas or n_dias:
        e = e.reduzir(n_campanhas=n_campanhas, n_dias=n_dias)
    m = gerar_mundo(e.mundo, seed, orcamento_diario_micros=orcamento_diario_micros)
    return Simulacao(e, int(seed), m, observar(m, e.observador, cenario=e.nome))


__all__ = [
    "ADVERSARIAIS", "CAMPOS_CONTRATO", "CAMPOS_EXTRAS", "CATALOGO", "Campanha", "DISPOSITIVOS", "EspecCenario",
    "FAIXAS_FORMA", "FONTES", "FONTES_PARAMETROS", "Gabarito", "JanelaForaDoAr", "Leituras", "METRICAS_HORARIAS",
    "MudancaOrcamento", "Mundo", "NOMES", "PAISES", "ParametrosMundo", "ParametrosObservador", "QuebraRegime",
    "RegistroObservacao", "STATUS", "STATUS_COM_VALOR", "STATUS_SEM_VALOR", "Simulacao", "VERSAO_CATALOGO",
    "VERSAO_SIMULADOR", "catalogo_sha256", "cenario", "chave_fato", "gerar_mundo", "id_campanha", "id_conta", "iso",
    "medir_forma", "observar", "para_observacao_contrato", "registros_contrato", "simular", "soma_ingenua",
    "somar_por_moeda", "verificar_forma", "visao_as_of",
]
